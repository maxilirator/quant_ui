<script lang="ts" context="module">
  export type Bin = { start: number; end: number; count: number };
</script>

<script lang="ts">
  export let bins: Bin[] = [];
  export let total = 0;
  export let height = 140;
  export let valueFormat: (v: number) => string = (v) =>
    (v * 100).toFixed(2) + "%";
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  function pct(count: number) {
    return ((count / (total || 1)) * 100).toFixed(1) + "%";
  }
  let hover: Bin | null = null;
</script>

<div
  class="hist"
  role="list"
  style={`--h:${height}px`}
  on:mouseleave={() => (hover = null)}
>
  {#each bins as b}
    <div
      class="bar"
      role="listitem"
      style={`--v:${b.count / maxCount};`}
      on:mousemove={() => (hover = b)}
      title={`${valueFormat(b.start)} – ${valueFormat(b.end)}\n${b.count} (${pct(b.count)})`}
    ></div>
  {/each}
  {#if !bins.length}
    <p class="empty">No distribution</p>
  {/if}
</div>
{#if hover}
  <div class="legend">
    {valueFormat(hover.start)} – {valueFormat(hover.end)} • {hover.count} ({pct(
      hover.count
    )})
  </div>
{/if}

<style>
  .hist {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    width: 100%;
    height: var(--h);
    position: relative;
  }
  .bar {
    flex: 1;
    background: linear-gradient(to top, #38bdf8, #0ea5e9);
    height: calc(var(--v) * 100%);
    border-radius: 2px 2px 0 0;
    position: relative;
  }
  .bar:hover {
    outline: 1px solid #fff;
  }
  .empty {
    font-size: 0.65rem;
    color: rgba(148, 163, 184, 0.6);
    margin: 0;
  }
  .legend {
    margin-top: 0.4rem;
    font-size: 0.65rem;
    color: #cbd5e1;
  }
</style>
