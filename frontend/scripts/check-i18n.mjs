import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "i18n", "messages");
const locales = ["he", "ar", "en"];

function flatten(value, prefix, out) {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) flatten(child, prefix ? `${prefix}.${key}` : key, out);
  } else {
    out.set(prefix, value);
  }
  return out;
}

const tables = Object.fromEntries(
  locales.map((locale) => [locale, flatten(JSON.parse(readFileSync(join(dir, `${locale}.json`), "utf8")), "", new Map())]),
);

const allKeys = new Set(locales.flatMap((locale) => [...tables[locale].keys()]));
const problems = [];
for (const key of [...allKeys].sort()) {
  for (const locale of locales) {
    const value = tables[locale].get(key);
    if (value === undefined) problems.push(`${locale}: missing ${key}`);
    else if (typeof value !== "string" || !value.trim()) problems.push(`${locale}: empty or non-string ${key}`);
  }
}

if (problems.length) {
  console.error(problems.join("\n"));
  console.error(`\n${problems.length} i18n problem(s)`);
  process.exit(1);
}
console.log(`i18n: ${allKeys.size} keys, identical in ${locales.join(", ")}`);
