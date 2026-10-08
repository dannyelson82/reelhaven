# 0027: The wizard doesn't wait for a library to be read

- Status: accepted
- Date: 2026-10-08

## Context
The owner tested the setup wizard (ADR-0026) on real libraries. Its scan step
waited for the whole library to be read before *Next* unlocked. A first scan
reads every file: a few minutes for a few thousand films, but up to an hour
for a TV library of 30,000+ episodes on an Unraid array. Only the size and
quality estimates need the files' details; the language questions don't.

## Decision
- The wizard moves on as soon as the files have been **listed**. Reading
  carries on in the background (it already did when the page was left).
- The **size and quality** and **audio** steps wait for the first 200 files
  (or all of them, if fewer). From then on they show estimates from the files
  read so far, scaled to the whole library by size, labelled *estimated from
  X of Y files*, and refreshed every 15 seconds while reading continues.
- The **test run** picks its samples from files already read.
- **Going Automatic before reading finishes is allowed.** Nothing is processed
  until a file's original language has been looked up, which happens at the
  end of a scan (the guard added in PR #60); the last steps say so.
- Options not chosen: keep waiting with a better progress bar (up to an hour
  of waiting on large libraries); read a random sample of ~500 files first
  (fast, but a second code path for estimates).

## Consequences
- Estimates on a large library start rough and settle as reading continues.
- The estimate endpoint reports the reading progress (files read, files to
  read, size of every file found) while a scan runs.
