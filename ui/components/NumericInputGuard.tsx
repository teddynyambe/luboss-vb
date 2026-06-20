'use client';

import { useEffect } from 'react';

/**
 * Mounts a single window-level listener that defuses two well-known
 * footguns of `<input type="number">`:
 *
 * 1. Wheel-scroll silently changing the focused value — a member
 *    scrolling the page should NEVER turn their K2,000 declaration into
 *    K2,000,001. We blur the field on wheel so the scroll passes through
 *    to the page instead.
 *
 * 2. Arrow Up / Arrow Down also nudging the value when the input is
 *    focused. We block those keys for number inputs; users who genuinely
 *    want to type can still use the digit keys.
 *
 * Mount this once near the root of the app (e.g. inside RootLayout's body
 * wrapper). It registers `passive: false` listeners on window so it works
 * regardless of which page is currently rendered.
 */
export default function NumericInputGuard() {
  useEffect(() => {
    const isNumberInput = (el: EventTarget | null): el is HTMLInputElement =>
      el instanceof HTMLInputElement && el.type === 'number';

    const onWheel = (e: WheelEvent) => {
      const active = document.activeElement;
      if (isNumberInput(active) && active === e.target) {
        // Take focus off so the wheel scrolls the page instead of
        // mutating the value. Re-focusable with a tap/click.
        active.blur();
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      if (isNumberInput(e.target)) {
        e.preventDefault();
      }
    };

    // passive:false on wheel is intentional — we don't preventDefault
    // (which would block scrolling entirely), we just blur. Listed as
    // passive to keep page-scroll smooth.
    window.addEventListener('wheel', onWheel, { passive: true });
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('wheel', onWheel);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  return null;
}
