---
title: Hardware
order: 70
summary: Let ReelHaven use your graphics cards, and choose which devices encode.
---

# Hardware

Re-encoding is far faster on a graphics card (GPU) than on the CPU.
ReelHaven supports **NVIDIA** (NVENC), **Intel** (Quick Sync) and **AMD**
GPUs.

## Give the container your GPUs (Unraid)

Edit the ReelHaven container (Docker tab → ReelHaven icon → **Edit**, then
switch on **Advanced View**):

- **NVIDIA**: install the *Nvidia Driver* plugin first. Add
  `--runtime=nvidia` to **Extra Parameters** and set
  **NVIDIA_VISIBLE_DEVICES** to `all` (or one GPU's UUID). Leave
  **NVIDIA_DRIVER_CAPABILITIES** at `compute,video,utility`.
- **Intel or AMD**: click **Add another Path, Port, Variable, Label or
  Device**, choose **Device**, and enter `/dev/dri`.

Click **Apply**. If an Intel processor's built-in graphics don't show up, they
may be switched off in the motherboard's BIOS (often when a graphics card is
installed). Look for a setting like **iGPU Multi-Monitor**.

## The Hardware page

When ReelHaven starts, it runs a one-second test encode on every device for
every format (HEVC 8-bit, HEVC 10-bit, AV1 8-bit, AV1 10-bit, H.264). The page
shows what really works inside the container: a tick with the encoder's name,
or **not supported**. Hover over *not supported* to see why, for example
"No capable devices found" for AV1 on an older GPU. Click **Detect again**
after changing the container or drivers.

For each device:

- **Use for encoding** switches the device on or off.
- **At the same time** is how many files it encodes at once (default 2 per
  GPU). Lower it if Plex or Jellyfin playback stutters while ReelHaven works;
  consumer NVIDIA cards also limit simultaneous encodes. A card has one
  encoding engine, so once it's fully busy, more files at once don't finish
  any sooner. 2 or 3 is usually the sweet spot.
- The CPU is off by default (**Allow CPU encoding (slow)**). It's useful for
  AV1 on GPUs that can't encode it, or when there's no GPU.

When several devices can do a job, ReelHaven prefers NVIDIA, then Intel, then
AMD, then the CPU. A device is only given jobs whose format it passed the test
for.

GPUs are much faster than the CPU, but at the same quality their files are
somewhat larger: in our measurements about 15 % for NVIDIA and up to 55 % for
older Intel graphics (UHD 630). The quality looks the same; you just save a
little less space.

### Decoding on the GPU too

To re-encode a file, ReelHaven first has to decode (unpack) the original
video. It does that on the same graphics card that encodes, NVIDIA, Intel or
AMD, so the CPU stays almost idle. This works for nearly every file: H.264,
HEVC (including 10-bit and HDR), VP9, AV1 (on newer cards: RTX 30, Intel 11th
generation, AMD RX 6000 and later), MPEG-2 and VC-1. The few files a card
can't decode, such as 10-bit H.264 ("Hi10P", common in anime), are decoded by
the CPU instead. If decoding on the card fails for any reason, the file is
simply tried again with the CPU, so nothing is lost. The [Jobs](jobs.md) page
shows which was used.

## CPU limit

Some work always runs on the CPU, even with graphics cards: CPU encodes, files
a card can't decode (for example 10-bit H.264), audio conversion, quality
checks after a test encode, and reading new files.

- ReelHaven always runs this work at **low priority**, so Plex, the Unraid web
  interface and your other containers get the CPU first whenever they need it.
  When the server is otherwise idle, ReelHaven may use all of it.
- **Limit CPU cores** (on the Hardware page) also caps how many cores it may
  use at all, for example 3 of 6. Turning it on starts at half your cores;
  change **Cores to use** as you like. ReelHaven uses the last cores, since
  Unraid and other containers tend to favour the first ones.
- A change applies to jobs that start afterwards; running ones keep their
  cores until they finish.
- If Unraid's own CPU pinning (Docker → ReelHaven → **Edit** → **CPU Pinning**)
  already limits the container, the page counts only the cores it was given.

## Check that your GPUs really work

Do this once after setting up the container, and again after changing
drivers, the BIOS or the container settings.

1. Open **Hardware** and click **Detect again**. Each GPU should show a tick
   for **HEVC 8-bit** and **HEVC 10-bit**. AV1 needs a recent GPU (NVIDIA RTX
   40 series, Intel Arc or newer); *not supported* there is normal on older
   cards.
2. Pick a small library (or make one with a few copies of files) and give it
   a [profile](profiles.md).
3. To test one GPU on its own, switch **Use for encoding** off for the
   others, then start a [test run](test-run.md) with 1 file. The result shows
   which device encoded it (for example *nvidia:0*) and how fast.
4. Look at the rating and the still frames. Repeat for each GPU, then switch
   them all back on.
5. Optional: apply one file from its details, check it plays in Plex or
   Jellyfin, then try **Restore** in the [recycle bin](recycle-bin.md).

If a GPU is missing or every format fails, check the container settings at
the top of this page, then look at the error by hovering over *not
supported*.
