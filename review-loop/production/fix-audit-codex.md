## Findings

- **HIGH — Non-US layouts can be replaced by GNOME’s US fallback when IBus is unavailable.** After setup, layouts are IBus sources. The plan’s supplied facts say GNOME skips a source whose engine it cannot reach and falls back to `us`; the README also documents this during startup or an IBus crash. For someone relying on a non-US layout, that means they can lose their working layout. Documenting the risk does not meet the goal to never lose a working keyboard. I could not verify GNOME 50 behavior on the target desktop.

- **HIGH — Install overwrites a foreign shortcut at the reserved path.** I reproduced this using the installer test setup: with the shortcut named “Emoji Picker” but its command set to `/usr/bin/gnome-characters`, `install.sh --root …` succeeded and replaced its command and binding. The installer checks only the name before later writing all three fields ([install.sh](/home/frank/.cache/ep-review-prod/r3/audit/install.sh:71), [install.sh](/home/frank/.cache/ep-review-prod/r3/audit/install.sh:180)). This conflicts with the plan’s requirement to refuse a shortcut it did not make and loses the user’s shortcut.

## Plan coverage

The install layout, versioned upgrade, per-user layout registry, source conversion, deferred setup, shortcut handling, uninstall flow, doctor command, logging, accessible labels, copy messages, and README items are present in the inspected code.

One plan item is absent from the tree: the Wayland “Round 3” human-feedback guide described in [PLAN.md](/home/frank/.cache/ep-review-prod/r3/audit/review/PLAN.md:154). I also could not verify GNOME 50 behavior here; the README says it was tested on Ubuntu 26.04, but the supplied machine information only describes Ubuntu 24.04 X11.

## Declined findings

1. **HOLDS.** Uninstall removes the shortcut when its name and command identify this app, even if its binding changed. That avoids leaving a shortcut pointing at a launcher uninstall deletes.
2. **HOLDS, with GNOME 50 unverified.** The desktop entry and application ID are present and match; the supplied owner rationale for GNOME window naming and icons is consistent with the code.
3. **HOLDS, with GNOME 50 unverified.** The code converts both source lists in order. Per the stated Shell behavior, changing write order cannot update an already populated in-memory MRU list. The note also acknowledges that the first layout may become active after the swap.
4. **HOLDS.** The implementation stages versioned directories and switches the `current` symlink with a rename. Replacing a non-empty directory with `mv -T` would not provide the claimed atomic upgrade.
5. **DOES NOT HOLD.** Avoiding a second plain layout may avoid an indicator for a single layout, but the fallback can leave non-US users with the wrong layout when IBus is unavailable. Documentation does not prevent that user impact.

## Verification

Ran the requested unittest command: **63 tests passed, 1 skipped**. The skipped test and private IBus behavior were not verified in this environment. The foreign-shortcut scenario was reproduced separately with the tests’ temporary root and keyfile settings.