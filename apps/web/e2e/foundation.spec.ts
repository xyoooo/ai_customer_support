import { expect, test } from "@playwright/test";

test("owner can register and open the isolated workspace", async ({ page }) => {
  const suffix = Date.now().toString();
  await page.goto("/register");
  await page.getByLabel("Display name").fill("Demo Owner");
  await page.getByLabel("Email").fill(`demo-${suffix}@example.com`);
  await page.getByLabel("Password").fill("a-secure-demo-password");
  await page.getByLabel("Workspace name").fill("Demo Support");
  await page.getByLabel("Workspace slug").fill(`demo-${suffix}`);
  await page.getByRole("button", { name: "Create workspace" }).click();

  await expect(page.getByRole("heading", { name: /Good morning, Demo Owner/ })).toBeVisible();
  await expect(page.getByText("RLS active")).toBeVisible();
  await page.getByRole("link", { name: /Demo Support/ }).click();
  await expect(page.getByRole("heading", { name: "Demo Support" })).toBeVisible();
  await expect(page.getByText(`demo-${suffix}@example.com`)).toBeVisible();
});

