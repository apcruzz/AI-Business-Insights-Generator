// Shared DOM, formatting, grouping, and statistics helpers used by dashboard.js.
// Finds one element on the page by its id.
export const $ = (id) => document.getElementById(id);

// Escapes user-provided text before placing it inside HTML.
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

// Adds one numeric column across a set of rows.
export const sum = (rows, key) =>
  rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);

// Groups rows by a field, for example all rows for each product or category.
export const group = (rows, key) => [
  ...rows.reduce((map, row) => {
    const value = row[key];
    if (!map.has(value)) map.set(value, []);
    map.get(value).push(row);
    return map;
  }, new Map()),
];

// Formats a percent value and handles missing or invalid numbers cleanly.
export const pct = (value) => (Number.isFinite(value) ? value.toFixed(1) + "%" : "-");

// Rounds a number to two decimal places for calculations and AI facts.
export const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100;

// Weekday labels follow JavaScript Date.getUTCDay(): Sunday is index zero.
export const dayNames = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

export function sourceOptions(select, options, defaultValue = "") {
  // Rebuild a dropdown from scratch so old choices do not remain.
  select.replaceChildren();
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Not provided";
  select.append(blank);
  options.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
  select.value = defaultValue;
}

export function period(hour) {
  // Buckets hours into the same time-of-day groups used by the filter.
  return hour < 6
    ? "overnight"
    : hour < 12
      ? "morning"
      : hour < 18
        ? "afternoon"
        : "evening";
}

export function weekKey(date) {
  // Converts a date into the Monday that starts its week.
  const value = new Date(date + "T12:00:00Z");
  value.setUTCDate(value.getUTCDate() - ((value.getUTCDay() + 6) % 7));
  return value.toISOString().slice(0, 10);
}

export function median(values) {
  // Finds the middle value for order-size and sales-consistency questions.
  const numbers = values
    .map(Number)
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (!numbers.length) return null;
  const middle = Math.floor(numbers.length / 2);
  return numbers.length % 2
    ? numbers[middle]
    : (numbers[middle - 1] + numbers[middle]) / 2;
}

export function standardDeviation(values) {
  // Measures how much values vary around their average.
  const numbers = values.map(Number).filter((value) => Number.isFinite(value));
  if (numbers.length < 2) return null;
  const average = numbers.reduce((total, value) => total + value, 0) / numbers.length;
  const variance =
    numbers.reduce((total, value) => total + (value - average) ** 2, 0) /
    numbers.length;
  return Math.sqrt(variance);
}

export function findNamed(items, question) {
  // Best-effort product/category lookup for questions naming a specific item.
  return items
    .filter((item) => item.name && question.includes(item.name.toLowerCase()))
    .sort((a, b) => b.name.length - a.name.length)[0];
}

export function topBy(items, key) {
  // Sorts largest-to-smallest for rankings like top products or top margins.
  return [...items]
    .filter((item) => item[key] !== null && item[key] !== undefined)
    .sort((a, b) => b[key] - a[key]);
}

export function bottomBy(items, key) {
  // Sorts smallest-to-largest, ignoring zero/missing values that are not useful.
  return [...items]
    .filter((item) => item[key] !== null && item[key] !== undefined && item[key] > 0)
    .sort((a, b) => a[key] - b[key]);
}

export function missingDataAnswer(topic, needed) {
  // Plainly explains that a question needs data the current dashboard does not collect.
  return `${topic} is not available from the mapped sales file. To answer it reliably, add ${needed} to the dataset or connect a matching source that contains it.`;
}
