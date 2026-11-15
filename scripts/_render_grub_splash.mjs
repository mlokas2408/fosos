import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const require = createRequire(join(process.env.TEMP || "/tmp", "fosos-resvg", "package.json"));
const { Resvg } = require("@resvg/resvg-js");

const repo = fileURLToPath(new URL("..", import.meta.url));
const grubDir = join(repo, "build/live-build/config/bootloaders/grub-pc");
const bootloaders = join(repo, "build/live-build/config/bootloaders");
const includes = join(repo, "build/live-build/config/includes.binary/boot/grub");
const themeLogo = join(repo, "packages/fosos-theme/usr/share/fosos/logo");

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">
  <rect width="800" height="600" fill="#0a0a0a"/>
  <g transform="translate(288,48) scale(0.438)">
    <path fill="#fafafa" d="M256 92c-88.4 0-160 71.6-160 160 0 35.2 11.4 67.8 30.7 94.2 24.8-57.8 71.5-93.3 131.7-116.8l152.9-59.7C386.9 123.4 324.9 92 256 92Z"/>
    <path fill="#fafafa" d="M192 420c0-76.8 19.5-127.1 58.2-151 31.8-19.7 70.3-22.4 121.8-22.4h44c-4 56.4-38.3 91.4-93.6 91.4h-36.8c-27.8 0-41.6 20.1-41.6 60.6v27.1Z"/>
  </g>
  <text x="400" y="310" text-anchor="middle" font-family="DejaVu Sans, Liberation Sans, Arial, sans-serif" font-size="36" font-weight="500" fill="#fafafa">FosOS</text>
  <text x="400" y="342" text-anchor="middle" font-family="DejaVu Sans, Liberation Sans, Arial, sans-serif" font-size="14" fill="#a1a1a1" letter-spacing="3">phos · light</text>
</svg>
`;

mkdirSync(grubDir, { recursive: true });
mkdirSync(includes, { recursive: true });
mkdirSync(themeLogo, { recursive: true });

const svgPath = join(grubDir, "splash.svg");
writeFileSync(svgPath, svg, "utf8");

const resvg = new Resvg(Buffer.from(svg, "utf8"), {
  fitTo: { mode: "width", value: 800 },
  font: { loadSystemFonts: true },
});
const png = resvg.render().asPng();
const pngPath = join(grubDir, "splash.png");
writeFileSync(pngPath, png);

mkdirSync(join(bootloaders, "grub-efi"), { recursive: true });
copyFileSync(pngPath, join(bootloaders, "grub-efi", "splash.png"));
copyFileSync(pngPath, join(includes, "splash.png"));
copyFileSync(pngPath, join(includes, "fosos-logo.png"));
copyFileSync(pngPath, join(themeLogo, "fosos-boot-splash.png"));

console.log("wrote", pngPath, `(${png.length} bytes)`);
