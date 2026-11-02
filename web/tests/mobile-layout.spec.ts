import { expect, test } from "@playwright/test";

const pages = [
  { path: "/", name: "home" },
  { path: "/docs", name: "docs" },
  { path: "/privacy", name: "privacy" },
];

const widths = [360, 390, 430];

for (const { path, name } of pages) {
  for (const width of widths) {
    test(`${name} fits a ${width}px screen`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(path);

      const widerThanScreen = await page.evaluate(() => {
        const pageWidth = document.documentElement.scrollWidth;
        const screenWidth = document.documentElement.clientWidth;
        return pageWidth > screenWidth;
      });

      const headerHeight = await page.getByRole("banner").evaluate((el) => {
        return el.getBoundingClientRect().height;
      });
      expect(headerHeight).toBeLessThanOrEqual(64);

      await page.screenshot({
        path: `test-results/mobile-${name}-${width}.png`,
        fullPage: true,
      });
      expect(widerThanScreen).toBe(false);
    });
  }
}
