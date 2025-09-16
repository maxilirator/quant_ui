<script lang="ts">
  export let dates: string[] = [];
  export let values: number[] = [];
  export let height = 140;
  const maxAbs = Math.max(0.0001, ...values.map((v) => Math.abs(v)));
  const scale = (v: number) => (v / maxAbs) * (height / 2 - 10);
</script>

<div class="returns-chart" style={`--h:${height}px`}>
  {#each values as v, i}
    <span
      class="bar"
      style={`--v:${scale(v)};`}
      title={`${dates[i]}: ${(v * 100).toFixed(2)}%`}
    ></span>
  {/each}
</div>

<style>
  .returns-chart {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: var(--h);
    background: rgba(15, 23, 42, 0.55);
    border: 1px solid rgba(30, 41, 59, 0.6);
    padding: 4px 4px 0;
    border-radius: 0.75rem;
    overflow: hidden;
    position: relative;
  }
  .returns-chart::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(255, 255, 255, 0.15);
  }
  .bar {
    flex: 1;
    background: linear-gradient(180deg, #818cf8, #38bdf8);
    height: calc(var(--v) + 50%);
    transform-origin: bottom;
    opacity: 0.85;
  }
  .bar[style*="-"] {
    background: linear-gradient(180deg, #f87171, #fb923c);
  }
</style>
