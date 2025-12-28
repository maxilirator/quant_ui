from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def init_qlib(provider_uri: str) -> None:
    try:
        import qlib
    except ImportError as exc:
        raise RuntimeError("qlib is required; install qlib or your q-training library") from exc

    qlib.init(provider_uri=provider_uri)
