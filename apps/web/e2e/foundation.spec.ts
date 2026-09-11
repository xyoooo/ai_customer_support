import { expect, test } from "@playwright/test";

test("owner can register and open the isolated workspace", async ({ page }) => {
  test.setTimeout(90_000);
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

  await page.getByLabel("Display name").fill("Synthetic support guide");
  await page.getByLabel("Document file").setInputFiles({
    name: "support-guide.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Synthetic support guide\n\nReturns are accepted for 30 days.\n"),
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  const documentLink = page.getByRole("link", { name: /Synthetic support guide/ });
  await expect(documentLink).toBeVisible();
  await expect(documentLink.getByText("active")).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("Question").fill("How long are returns accepted?");
  await page.getByRole("button", { name: "Search evidence" }).click();
  await expect(page.getByText(/Returns are accepted for 30 days/)).toBeVisible({
    timeout: 30_000,
  });
  await documentLink.click();
  await expect(page.getByRole("heading", { name: "Synthetic support guide" })).toBeVisible();
  await expect(page.getByText("Version 1")).toBeVisible();
  await expect(page.getByText("completed")).toBeVisible();
});
