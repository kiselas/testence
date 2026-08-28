import { expect, test } from "@playwright/test";


test("add a named row", async ({ page }) => {
  await test.step("open the page", async () => {
    await page.goto("/index.html");
  });
  await test.step("increment the counter", async () => {
    await page.getByRole("button", { name: "inc", exact: true }).click();
  });
  await test.step("counter shows 1", async () => {
    await expect(page.locator("#count")).toHaveText("1");
  });
  await test.step("enter a name", async () => {
    await page.getByPlaceholder("name", { exact: true }).fill("alice");
  });
  await test.step("add the named row", async () => {
    await page.getByRole("button", { name: "add", exact: true }).click();
  });
  await test.step("the named row appears", async () => {
    await expect(page.locator("#list li").last()).toHaveText("row-alice");
  });
});
