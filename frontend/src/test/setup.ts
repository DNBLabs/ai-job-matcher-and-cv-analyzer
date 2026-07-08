import "@testing-library/jest-dom/vitest";
import { fireEvent } from "@testing-library/dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Radix DropdownMenu opens on pointerdown; jsdom click omits it.
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};

const nativeClick = fireEvent.click.bind(fireEvent);
fireEvent.click = (element, options) => {
  fireEvent.pointerDown(element, {
    button: 0,
    ctrlKey: false,
    pointerType: "mouse",
  });
  return nativeClick(element, options);
};

// vite.config sets globals:false, so Testing Library's auto-cleanup hook is not
// registered. Tear down the rendered DOM between tests explicitly.
afterEach(cleanup);
