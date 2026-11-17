---
version: alpha
name: "MiniDeck"
description: "A compact, dark macropad interface for controlling a computer from a phone."
colors:
  primary: "#60a5fa"
  background: "#0f1216"
  surface: "#171c23"
  surfaceRaised: "#1f2630"
  border: "#2a323e"
  text: "#e8ecf2"
  muted: "#8a93a3"
  success: "#4ade80"
  danger: "#f87171"
typography:
  sans:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro', 'Segoe UI', Roboto, sans-serif"
  mono:
    fontFamily: "ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, monospace"
rounded:
  DEFAULT: "18px"
  control: "999px"
spacing:
  topbar-inline: "18px"
  grid-inline: "20px"
  grid-gap: "12px"
components:
  macropad-key:
    backgroundColor: "surface"
    textColor: "muted"
    rounded: "DEFAULT"
  icon-button:
    backgroundColor: "background"
    textColor: "text"
    rounded: "control"
  toast:
    backgroundColor: "surfaceRaised"
    textColor: "text"
    rounded: "DEFAULT"
---

# MiniDeck Design System

## Overview

### Creative North Star

MiniDeck should feel like a small physical macropad: dark hardware, sharply legible labels, and a restrained glow only where a configured key signals its own action or live state.

### Product context and register

- **Audience and primary job:** People using a phone or tablet as a fast control surface for their own Mac, PC, media, or home-automation workflows.
- **Locale(s) and language policy:** Spanish and English are supported. All product-owned copy and accessible names follow the active locale; user-configured button labels are not translated.
- **Usage scene:** Primarily a narrow, touch-first screen at arm's reach, with a desktop browser and a macOS menu-bar shell as secondary surfaces.
- **Register:** Product utility. Familiar controls and predictable feedback take precedence over brand decoration.
- **Memorable signature:** Each macropad key owns its LED accent through `--led`.
- **Restraint:** The top bar, navigation, forms, and overlays stay quiet so the deck keys remain the primary visual signal.
- **Anti-references:** Avoid generic dashboard cards, decorative gradients, and broad colored glows unrelated to a key's configured LED state.
- **Token ownership/runtime mapping:** `frontend/style.css` is the runtime source of truth. This document records its shared CSS custom properties; it does not generate CSS.

## Colors

The permanent shell uses `background`, `surface`, `surfaceRaised`, `border`, `text`, and `muted`. Green (`success`) and red (`danger`) communicate connection and failure states alongside text or icons. A key's configurable LED color is an expressive accent, not a replacement for status text.

## Typography

Use the system sans stack for controls and labels so the interface follows each device naturally. Use the monospaced stack only for short system values. Keep labels concise and allow localized strings to use flexible layout rather than fixed character counts.

## Layout

The grid owns the available deck space and keeps keys usable with a responsive row minimum. Top-bar and grid spacing are defined in `frontend/style.css`; safe-area padding protects installed mobile web apps. The same shell supports phone, tablet, and desktop without separate visual variants.

## Elevation & Depth

Hierarchy comes from tonal surfaces and borders. The only colored glow is the LED treatment attached to an individual macropad key or connection indicator; it communicates the configured control state rather than decorating containers.

## Shapes

Macropad keys use the 18px radius defined by `--radius`; page tabs use a pill shape. Avoid adding new radius families without a functional reason.

## Components

### Foundational visual states

Interactive controls retain native button behavior and visible labels or localized accessible names. Connection and action failures use the existing toast system, and dynamic widget states reuse the same translation catalog as the shell.

### Buttons and actions

Deck keys are the primary actions. Compact icon controls in the top bar must provide a localized title and accessible name. Destructive actions remain visually distinct from normal editing actions.

### Navigation and data display

Page tabs use the muted/active surface contrast. The horizontal tab row may scroll on narrow screens without hiding the current page.

### Forms and overlays

The editor sheet, pairing dialog, and toast use existing MiniDeck patterns. New copy belongs in `frontend/i18n.js`, rather than being embedded in a widget or overlay.

### Iconography

Use Lucide/Iconify icons or user-configured emoji. Icon-only controls need a localized title and accessible name.

### Motion

Motion is short feedback: pressed keys, page transitions, and state changes. It should never delay a control action.

### Content and data visualization

Write direct, action-oriented labels. The web and macOS menu use the same language names—English and Español—so users can recover from an unwanted saved choice.

## Do's and Don'ts

- **Do:** Reuse the active locale for dynamic widget copy, errors, placeholders, titles, and accessible names.
- **Do:** Preserve the existing macropad grid and per-key LED language across every screen.
- **Don't:** Add a new hardcoded Spanish or English UI string outside the translation catalog.
- **Don't:** Use colored visual effects on static containers; reserve LED color for key or connection state.
