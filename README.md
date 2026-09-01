# MnM Party Meter

An external, OCR-based party damage meter for **Monsters & Memories**.

MnM Party Meter reads visible combat-log text from a user-selected area of the screen and turns outgoing damage into a simple live party meter. It was built primarily for beta testing, group play, and understanding how class damage changes across different stages of progression.

## How It Works

MnM Party Meter uses **OCR (Optical Character Recognition)** to read the combat text already visible on your screen.

The meter:

- Captures only the screen region you select.
- Uses Tesseract OCR to recognize visible combat-log text.
- Identifies outgoing damage events.
- Attributes recognized damage to configured party members and pets.
- Displays party damage totals in a lightweight overlay.

All combat-log processing happens locally on your computer.

## Safety and Game Interaction

MnM Party Meter is an **external screen-reading utility**.

It does **not**:

- Read or modify Monsters & Memories process memory.
- Inject code into the game.
- Inspect or intercept network traffic.
- Read game files to obtain combat information.
- Send commands to the game.
- Automate gameplay or player input.
- Require your Monsters & Memories account credentials.
- Upload your combat data to a remote service.

The program only analyzes pixels from the screen area that you explicitly designate for OCR.

The Python source used by the meter is included in this repository so that users can inspect how it works.

## Why Two Combat Windows?

For the best results, MnM Party Meter uses two nearby combat-log windows in Monsters & Memories:

**Other** — outgoing damage from the other members of your party.

**My** — your outgoing damage and your pet's outgoing damage.

You then select **one OCR capture region around both windows**.

This split is intentional. A single combat window containing an entire party's damage can scroll extremely quickly. Separating your damage from the rest of the party reduces the amount of text moving through each window and gives OCR more opportunity to read combat events before they leave the screen.

The two windows do not need to scroll at the same speed. In a full party, Other will normally move considerably faster than My.

Different scroll speeds do not inherently create duplicate damage events.

## OCR Refresh Rate

The recommended starting refresh rate is **300 ms**.

Faster scanning can help when the Other window is moving particularly quickly, but it also requires more processing power. Slower scanning reduces processing load but increases the possibility that rapidly scrolling combat text will leave the screen before OCR reads it.

Because this is screen-based OCR, no OCR damage meter can guarantee perfect recognition under every combat, display, or UI condition.

## Duplicate Protection

The meter maintains information about recently recognized combat events so that a line remaining visible across multiple OCR captures is not intended to be counted repeatedly.

When an encounter is reset, the meter also establishes a new baseline from the combat text already visible on screen. Existing lines are treated as pre-reset text so that the next encounter begins with newly appearing combat events rather than rereading the previous fight.

## Pets

Named pets can be assigned to their owner in the meter's setup screen.

Enter the pet's combat-log name in the **Pet name(s)** field for that player. Multiple pet names can be entered when necessary.

### Enchanter and Bard Charm

Charmed creatures can be more difficult to attribute because another player's charm may appear in the combat log under the creature's own name rather than as "your pet" or "party member's pet."

For the most reliable tracking:

1. Charm a creature that your party is **not also actively fighting**.
2. Enter that creature's name in the player's **Pet name(s)** field.
3. Avoid using a commonly fought creature as the mapped charm target.

If the party is fighting several creatures with the same name as the charmed pet, screen text alone may not contain enough information to reliably distinguish the charmed creature from hostile creatures.

## What This Tool Is For

The goal is not to call individual players out for low damage.

MnM Party Meter is intended to help players understand questions such as:

- How do classes perform on a fresh server with very little gear?
- How does damage change as characters gain levels, spells, weapons, and equipment?
- How much damage is contributed by pets, dots, procs, and other abilities?
- How does party damage change between early, mid, and later progression?
- How do different group compositions affect damage output?

A single damage result should not be treated as a definitive class ranking. Level, equipment, encounter length, target selection, group composition, player role, downtime, and many other factors can substantially affect damage.

## Installation

Windows users should download the current packaged version from the repository's **Releases** section rather than downloading the source repository ZIP.

The Windows package includes an installer that prepares the required application environment and checks for Tesseract OCR.

If a compatible Tesseract installation already exists, the installer can reuse it.

### Updating

To install a newer version:

1. Close MnM Party Meter.
2. Extract the new release ZIP.
3. Run `INSTALL - START HERE.cmd`.
4. Continue using the MnM Party Meter desktop shortcut.

You should not need to uninstall Python, Tesseract, or the previous meter version before updating.

## Setup Guide

The complete illustrated setup and beta-testing guide is available in the `docs` folder and with the Windows release.

It covers installation, combat-window configuration, OCR selection, party and pet setup, refresh rates, accuracy considerations, charm pets, and interpreting results.

## Source

The primary application source is available in:

`src/main.py`

Python dependencies are listed in:

`src/requirements.txt`

## Third-Party Software

MnM Party Meter is built with open-source software, including:

- Python
- Tesseract OCR
- PySide6 / Qt
- pytesseract
- Pillow
- MSS

Licenses, acknowledgments, and project links are provided in `THIRD_PARTY_NOTICES.md`.

Thank you to the developers and contributors who maintain these projects and make tools like this possible.

## Status

MnM Party Meter is an independent community utility created for use with Monsters & Memories.

It is not affiliated with, endorsed by, or an official product of the Monsters & Memories development team.