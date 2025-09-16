<script lang="ts">
  export interface Series {
    name: string;
    points: { x: string | number | Date; y: number }[];
    color?: string;
  }
  export let series: Series[] = [];
  export let height = 160;
  export let strokeWidth = 2;
  export let showDots = false;
  export let yFormat: (y: number) => string = (y) => y.toFixed(2);
  const COLORS = ["#38bdf8", "#818cf8", "#f472b6", "#fb923c", "#4ade80"];

  $: flat = series.flatMap((s) => s.points);
  $: xs = flat.map((p) => new Date(p.x as any).getTime());
  $: ys = flat.map((p) => p.y);
  $: minX = Math.min(...xs);
  $: maxX = Math.max(...xs);
  $: minY = Math.min(...ys);
  $: maxY = Math.max(...ys);
  $: spanX = maxX - minX || 1;
  $: spanY = maxY - minY || 1;
  $: width = 640; // fixed viewBox width; responsive via CSS

  function pathFor(points: Series["points"]) {
    return points
      .map((p, i) => {
        const x = ((new Date(p.x as any).getTime() - minX) / spanX) * width;
        const y = height - ((p.y - minY) / spanY) * height;
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }

  let hover: {
    x: number;
    y: number;
    sx: number;
    sy: number;
    series: string;
    value: number;
  } | null = null;

  function handleMove(e: MouseEvent, s: Series) {
    if (!showDots) return;
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const pts = s.points.map((p) => ({
      t: new Date(p.x as any).getTime(),
      y: p.y,
    }));
    const targetTime = minX + (relX / rect.width) * spanX;
    let nearest = pts[0];
    let diff = Math.abs(nearest.t - targetTime);
    for (const pt of pts) {
      const d = Math.abs(pt.t - targetTime);
      if (d < diff) {
        nearest = pt;
        diff = d;
      }
    }
    const sx = ((nearest.t - minX) / spanX) * width;
    const sy = height - ((nearest.y - minY) / spanY) * height;
    hover = {
      x: nearest.t,
      y: nearest.y,
      sx,
      sy,
      series: s.name,
      value: nearest.y,
    };
  }
</script>

<div class="chart-wrapper">
  <svg
    viewBox={`0 0 ${width} ${height}`}
    preserveAspectRatio="none"
    class="chart"
    on:mousemove={(e) => series[0] && handleMove(e, series[0])}
    on:mouseleave={() => (hover = null)}
  >
    {#each series as s, i}
      <path
        d={pathFor(s.points)}
        stroke={s.color || COLORS[i % COLORS.length]}
        fill="none"
        stroke-width={strokeWidth}
        vector-effect="non-scaling-stroke"
      />
    {/each}
    {#if hover}
      <g>
        <circle
          cx={hover.sx}
          cy={hover.sy}
          r={4}
          fill="#fff"
          stroke="#0ea5e9"
          stroke-width={2}
        />
        <line
          x1={hover.sx}
          x2={hover.sx}
          y1={0}
          y2={height}
          stroke="rgba(255,255,255,0.2)"
          stroke-width={1}
        />
      </g>
    {/if}
  </svg>
  {#if hover}
    <div class="tooltip" style={`left:${(hover.sx / width) * 100}%;top:0;`}>
      <strong>{hover.series}</strong><br />
      {yFormat(hover.value)}
    </div>
  {/if}
</div>

<style>
  .chart-wrapper {
    position: relative;
    width: 100%;
    max-width: 760px;
  }
  .chart {
    width: 100%;
    height: auto;
    display: block;
    overflow: visible;
  }
  .tooltip {
    position: absolute;
    transform: translate(-50%, 0);
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(56, 189, 248, 0.4);
    padding: 0.4rem 0.55rem;
    font-size: 0.65rem;
    border-radius: 0.4rem;
    pointer-events: none;
    color: #f1f5f9;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.4);
  }
  path {
    filter: drop-shadow(0 2px 6px rgba(56, 189, 248, 0.25));
    stroke-linejoin: round;
    stroke-linecap: round;
  }
</style>
