import { expect, test } from "@playwright/test";

const pages = [
  { path: "/", name: "home" },
  { path: "/docs", name: "docs" },
  { path: "/privacy", name: "privacy" },
];

for (const { path, name } of pages) {
  test(`${name} tap targets are at least 44px on a phone`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto(path);

    const result = await page.evaluate(() => {
        function isWordInASentence(link: Element) {
          if (link.tagName !== "A") return false;
          const paragraph = link.closest("p, li");
          if (!paragraph) return false;
          const otherWords = (paragraph.textContent ?? "").replace(link.textContent ?? "", "").trim();
          return otherWords.length > 0;
        }
      
        function boxesOverlap(a: DOMRect, b: DOMRect) {
          return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
        }
      
        const targets = [...document.querySelectorAll("button, a")].flatMap((button) => {
          if (isWordInASentence(button)) return [];
          const box = button.getBoundingClientRect();
          if (box.width === 0 && box.height === 0) return [];
          const name = button.getAttribute("aria-label") || button.textContent?.trim() || "unnamed button";
          return [{ name, box }];
        });
      
        const tooSmall = targets.flatMap(({ name, box }) => {
          if (box.width >= 44 && box.height >= 44) return [];
          return [`${name} is ${Math.round(box.width)} by ${Math.round(box.height)}`];
        });
      
        const overlapping: string[] = [];
        for (let i = 0; i < targets.length; i++) {
          for (let j = i + 1; j < targets.length; j++) {
            const first = targets[i];
            const second = targets[j];
            if (first && second && boxesOverlap(first.box, second.box)) {
              overlapping.push(`${first.name} overlaps ${second.name}`);
            }
          }
        }
      
        return { tooSmall, overlapping };
      });
      
      expect(result.tooSmall).toEqual([]);
      expect(result.overlapping).toEqual([]);
  });
}
