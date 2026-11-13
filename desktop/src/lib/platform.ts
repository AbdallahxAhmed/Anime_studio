/** Windows puts the primary button first; macOS and Linux desktops put it last. */
export const primaryFirst =
  typeof navigator !== "undefined" && navigator.userAgent.includes("Windows");
