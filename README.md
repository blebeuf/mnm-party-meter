# MnM Party Meter

External OCR-based party damage meter for **Monsters & Memories**.

MnM Party Meter reads visible combat-log text from a user-selected area of the screen and converts outgoing damage into a simple party meter. It does not read or modify game memory, inject code into the game, inspect network traffic, read game files for combat data, automate gameplay, or send commands to the game.

## How it works

The meter uses OCR (Optical Character Recognition) to read the combat text already visible on your screen. Combat-log processing happens locally on your computer.

For best results, use **two nearby MnM combat windows inside one OCR selection**:

- **Other (top):** outgoing damage from the rest of the party.
- **My (bottom):** your outgoing damage and your pet's outgoing damage.

### Combat window filters

**My window**
- Melee > Hit: **Me + Mine + Pet**
- Repeat **Me + Mine + Pet** under **Ability** and **Detrimental**.

**Other window**
- Melee > Hit: **NPCs + Players**
- Repeat **NPCs + Players** under **Ability** and **Detrimental**.

Using the same source split across Melee, Ability, and Detrimental is important for spells, abilities, DoTs, procs, and pet-related damage.

## v1.0.7

- Preserves the occurrence-aware duplicate protection validated in live testing.
- Legitimate identical hits can both count.
- Old visible damage does not become new damage just because the chat scrolls or sits on screen.
- Reset baselines visible text so old lines remain ignored.
- Keeps **My** on the proven direct reader path.
- Adds one conservative, bounded **Other-only** extra OCR sample when the Other pane is actively changing.
- Quiet Other windows with one additional party member stay on the normal path; busier groups can receive the extra sample automatically.
- 300 ms remains the recommended OCR refresh setting.

## Window sizing

Other and My can be approximately the same size. Keep several recent lines readable in both panes and keep the windows close together so one reasonably tight OCR rectangle can contain both. With especially heavy party traffic, a little extra vertical room for Other is optional rather than required.

## Charm pets

For Enchanter or Bard charm, MnM may show the charmed creature's name rather than its owner. For cleaner attribution, charm a creature you are not also actively fighting and enter that creature's exact name in the owner's **Pet name(s)** field.

## Safety and game interaction

MnM Party Meter is an external screen-reading utility. It does **not**:

- Read or modify Monsters & Memories process memory.
- Inject code into the game.
- Inspect or intercept network traffic.
- Read game files to obtain combat information.
- Send commands to the game.
- Automate gameplay or player input.
- Require Monsters & Memories account credentials.
- Upload combat data to a remote service.

The program only analyzes pixels from the screen area that you explicitly designate for OCR.

## Setup guide

See [`docs/MnM_Party_Meter_Setup_Guide_1.0.7.pdf`](docs/MnM_Party_Meter_Setup_Guide_1.0.7.pdf).

## Accuracy note

OCR is inherently imperfect and cannot reconstruct a line that was never captured. The meter biases toward conservative counting and duplicate prevention rather than inflating damage with ambiguous stale reads.

## Acknowledgments

Thanks to the developers and contributors behind Python, Tesseract OCR, PySide6 / Qt for Python, Pillow, MSS, pytesseract, and PyInstaller, and to the Monsters & Memories community members who tested the meter.

MnM Party Meter is an independent community utility and is not affiliated with, endorsed by, or an official product of Monsters & Memories or Niche Worlds Cult.
