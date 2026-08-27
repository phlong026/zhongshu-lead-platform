const YUAN_PER_WAN = 10_000;

export function amountToWan(value) {
  if (value == null || value === '') return '';
  const amount = Number(value);
  return Number.isFinite(amount)
    ? String(Number((amount / YUAN_PER_WAN).toFixed(4)))
    : '';
}

export function wanToAmount(value) {
  const text = String(value ?? '').trim();
  if (!text) return null;
  const amount = Number(text);
  return Number.isFinite(amount) ? Math.round(amount * YUAN_PER_WAN) : NaN;
}
