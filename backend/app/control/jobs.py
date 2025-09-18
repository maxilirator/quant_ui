"""In-memory job manager for executing whitelisted quant tasks.

Simplified for local use:
 - Executes tasks in a ThreadPool using subprocess (python -m <module> args)
 - Captures stdout/stderr (tail + full buffers capped)
 - Provides status transitions and cancellation (best-effort terminate)

Future enhancements: persistence, auth, websocket streaming, structured logs.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, Future
import subprocess, threading, uuid, time, os, sys, json

MAX_LOG_LINES = 4000
TAIL_LINES = 120


@dataclass
class JobRecord:
    id: str
    task_id: str
    argv: List[str]
    status: str = "queued"  # queued|running|succeeded|failed|cancelled
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    stdout: List[str] = field(default_factory=list)
    stderr: List[str] = field(default_factory=list)
    error: str | None = None
    cancelled: bool = False
    pid: int | None = None

    def to_public(self) -> Dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "error": self.error,
            "stdout_tail": self.stdout[-TAIL_LINES:],
            "stderr_tail": self.stderr[-TAIL_LINES:],
            "pid": self.pid,
        }


PERSIST_PATH_ENV = "QUANT_JOBS_STORE"
DEFAULT_JOBS_PATH = os.path.join("artifacts", "jobs", "jobs.jsonl")
MAX_HYDRATE = 400  # max historical jobs to load into memory


class JobManager:
    def __init__(self, max_workers: int = 2):
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="quant-job"
        )
        self._futures: Dict[str, Future] = {}
        self._persist_path = os.environ.get(PERSIST_PATH_ENV, DEFAULT_JOBS_PATH)
        self._ensure_persist_dir()
        self._hydrate_finished()

    # ---------------- Persistence -----------------
    def _ensure_persist_dir(self):
        try:
            d = os.path.dirname(self._persist_path)
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
        except Exception:
            pass  # best effort

    def _persist(self, rec: JobRecord):
        # Only persist terminal states
        if rec.status not in ("succeeded", "failed", "cancelled"):
            return
        try:
            payload = asdict(rec)
            # Trim large logs to tail to keep file size bounded
            if len(payload.get("stdout", [])) > 300:
                payload["stdout"] = payload["stdout"][-300:]
            if len(payload.get("stderr", [])) > 300:
                payload["stderr"] = payload["stderr"][-300:]
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            # Avoid crashing job finalize due to IO issues
            pass

    def _hydrate_finished(self):
        if not os.path.exists(self._persist_path):
            return
        try:
            lines: list[str] = []
            with open(self._persist_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    lines.append(line)
            # Keep only last MAX_HYDRATE lines
            for raw in lines[-MAX_HYDRATE:]:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                # Don't overwrite if an active job with same id (extremely unlikely)
                jid = data.get("id")
                if not jid or jid in self._jobs:
                    continue
                # Reconstruct JobRecord in finished state
                rec = JobRecord(
                    id=data.get("id"),
                    task_id=data.get("task_id", "unknown"),
                    argv=data.get("argv", []),
                    status=data.get("status", "succeeded"),
                    created_at=data.get("created_at", time.time()),
                    started_at=data.get("started_at"),
                    finished_at=data.get("finished_at"),
                    exit_code=data.get("exit_code"),
                    stdout=data.get("stdout", []),
                    stderr=data.get("stderr", []),
                    error=data.get("error"),
                    cancelled=data.get("cancelled", False),
                    pid=None,
                )
                self._jobs[jid] = rec
        except Exception:
            # Ignore hydrate failures
            pass

    def list(self) -> List[Dict]:
        with self._lock:
            return [j.to_public() for j in self._jobs.values()]

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def run(
        self,
        task_id: str,
        module: str,
        args: List[str],
        cwd: str | None = None,
        env: Dict[str, str] | None = None,
        python_exe: str | None = None,
    ) -> JobRecord:
        job_id = uuid.uuid4().hex
        py = python_exe or sys.executable
        argv = [py, "-m", module, *args]
        rec = JobRecord(id=job_id, task_id=task_id, argv=argv)
        with self._lock:
            self._jobs[job_id] = rec
        fut = self._executor.submit(self._execute, rec, cwd, env or {})
        with self._lock:
            self._futures[job_id] = fut
        return rec

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
        if not rec:
            return False
        rec.cancelled = True
        if rec.pid and rec.status == "running":
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(rec.pid), "/F", "/T"],
                        capture_output=True,
                    )
                else:
                    os.kill(rec.pid, 15)
            except Exception as e:  # pragma: no cover
                rec.stderr.append(f"[cancel] signal failed: {e}")
        return True

    # ------------------- internal ----------------------------------
    def _execute(
        self, rec: JobRecord, cwd: str | None, env_extra: Dict[str, str]
    ):  # pragma: no cover - side effects heavy
        rec.status = "running"
        rec.started_at = time.time()
        try:
            popen_env = os.environ.copy()
            popen_env.update(env_extra or {})
            proc = subprocess.Popen(
                rec.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=cwd or None,
                env=popen_env,
            )
            rec.pid = proc.pid
            assert proc.stdout and proc.stderr

            # Stream capture loops
            def _read(stream, target_list):
                for line in iter(stream.readline, ""):
                    if rec.cancelled:
                        break
                    line = line.rstrip("\n")
                    target_list.append(line)
                    if len(target_list) > MAX_LOG_LINES:
                        # truncate oldest
                        del target_list[0 : len(target_list) - MAX_LOG_LINES]
                stream.close()

            t_out = threading.Thread(
                target=_read, args=(proc.stdout, rec.stdout), daemon=True
            )
            t_err = threading.Thread(
                target=_read, args=(proc.stderr, rec.stderr), daemon=True
            )
            t_out.start()
            t_err.start()
            proc.wait()
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            rec.exit_code = proc.returncode
            if rec.cancelled:
                rec.status = "cancelled"
            elif proc.returncode == 0:
                rec.status = "succeeded"
            else:
                rec.status = "failed"
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        finally:
            rec.finished_at = time.time()
            # Persist terminal job state
            try:
                self._persist(rec)
            except Exception:
                pass


# Singleton accessor
_MANAGER: JobManager | None = None


def get_manager() -> JobManager:
    global _MANAGER
    if _MANAGER is None:
        workers = int(os.getenv("QUANT_CONTROL_MAX_WORKERS", "2"))
        _MANAGER = JobManager(max_workers=workers)
    return _MANAGER
