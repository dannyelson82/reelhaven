# 0014: Mantine as the UI toolkit

- Status: accepted
- Date: 2026-10-06

## Context
ADR-0005 chose React + TypeScript + Vite but no component library. The UI
needs forms, tables, modals, notifications, dark mode and charts.

## Decision
Use **Mantine** (core, form, notifications) and **@mantine/charts**, which is
built on Recharts (the charting library ARCHITECTURE.md names). Routing with
React Router, server state with TanStack Query.

## Consequences
- Complete, accessible components with built-in light and dark themes, which means less hand-written UI code.
- Mantine's look becomes ReelHaven's look; heavy custom styling would fight it.
