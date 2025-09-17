<script lang="ts">
  export interface MonthlyReturn {
    year: number;
    month: number;
    return: number;
  }
  export let data: MonthlyReturn[] = [];
  // Build year -> month map
  const years = Array.from(new Set(data.map((d) => d.year))).sort(
    (a, b) => a - b
  );
  const byYear: Record<number, (number | null)[]> = {};
  for (const y of years) {
    byYear[y] = Array(12).fill(null);
  }
  let min = Infinity;
  let max = -Infinity;
  for (const r of data) {
    byYear[r.year][r.month - 1] = r.return;
    if (r.return < min) min = r.return;
    if (r.return > max) max = r.return;
  }
  if (min === Infinity) {
    min = -0.01;
    max = 0.01;
  }
  function color(v: number | null) {
    if (v === null || isNaN(v)) return "rgba(148,163,184,0.12)";
    const t = (v - min) / (max - min || 1);
    // blue (neg) -> grey -> amber (pos)
    if (v < 0) {
      const a = Math.min(1, Math.max(0, -v / (Math.abs(min) || 1)));
      return `rgba(59,130,246,${0.15 + 0.55 * a})`;
    }
    const a = Math.min(1, Math.max(0, v / (max || 1)));
    return `rgba(234,179,8,${0.15 + 0.55 * a})`;
  }
  function fmt(v: number | null) {
    return v === null ? "" : (v * 100).toFixed(1) + "%";
  }
  const MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
</script>

<div class="heatmap">
  <div class="header first"></div>
  {#each MONTHS as m}<div class="header">{m}</div>{/each}
  {#each years as y}
    <div class="year">{y}</div>
    {#each byYear[y] as val, i}
      <div
        class="cell"
        style={`background:${color(val)}`}
        title={`${y} ${MONTHS[i]}\n${fmt(val)}`}
      >
        {fmt(val)}
      </div>
    {/each}
  {/each}
  {#if !years.length}
    <div class="empty">No monthly data</div>
  {/if}
</div>

<style>
  .heatmap {
    display: grid;
    gap: 2px;
    font-size: 0.6rem;
    align-items: center;
  }
  .header {
    font-weight: 600;
    text-align: center;
    padding: 0.2rem 0.1rem;
    letter-spacing: 0.05em;
  }
  .first {
  }
  .year {
    font-weight: 600;
    padding: 0.2rem 0.3rem;
    text-align: right;
  }
  .cell {
    min-width: 42px;
    text-align: center;
    padding: 0.35rem 0.15rem;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }
  .cell:hover {
    outline: 1px solid rgba(255, 255, 255, 0.35);
  }
  .empty {
    grid-column: 1 / -1;
    padding: 0.5rem 0;
    color: rgba(148, 163, 184, 0.55);
  }
</style>
