// Categorical / qualitative palette for the ANATOMY overlay. These colors encode
// organ/tissue IDENTITY only — a hue is just a name tag for a structure_id. They
// NEVER encode severity, probability, or any ordered magnitude. This is deliberately
// NOT a hot/inferno/viridis-style continuous scale and contains no pure red/green
// "alarm" pair: nothing here should read as a traffic-light pass/fail signal. The
// overlay labels anatomy; it does not detect, characterize, or exclude disease.
//
// ~12 medium-tone, translucent-friendly, mutually distinct hues (blue / amber /
// teal / mauve / brown / moss / gold / pink / olive …). Distinguishable when drawn
// at low alpha over a grayscale slice, and picked to avoid a red=bad / green=good
// reading.
const PALETTE = [
  '#4e79a7', // blue
  '#f28e2b', // amber
  '#76b7b2', // teal
  '#b07aa1', // mauve
  '#9c755f', // brown
  '#59a14f', // moss
  '#edc948', // gold
  '#ff9da7', // soft pink
  '#86bcb6', // pale teal
  '#a0cbe8', // pale blue
  '#8cd17d', // sage
  '#b6992d', // olive
]

// Resolve the display color for a region. Prefer the server-provided region.color
// (already a '#rrggbb' identity color from the provider); otherwise fall back to the
// categorical palette, cycling by index. Never derives color from any measurement.
export function colorForStructure(region, index) {
  return region?.color || PALETTE[index % PALETTE.length]
}

export default PALETTE
