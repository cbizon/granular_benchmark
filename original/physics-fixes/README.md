# Physics fixes

`0001-fix-bottom-spin-normal.patch` corrects the contact-vector sign in the
rotational branch for collisions with the moving bottom plate.

The stored bottom-wall normal points from the particle center toward the
contact point. Negating it makes a particle sliding in positive `x` acquire
negative `omega_y`; it also gives a nonzero surface velocity to an exact
rolling state. The corrected branch uses the stored normal directly.

Reference generation is required to run `balls-bench spin-gate` first. The
gate compiles the mechanically ported collision operator before and after the
patch, checks both against an independent Walton calculation, requires the
unfixed operator to exhibit the known defect, and requires the fixed operator
to pass all cases.

`0002-fix-random-initial-velocity.patch` removes the drive-amplitude bias from
fresh-run particle velocities. Each particle is assigned
`v_z ~ Uniform[-0.05, 0.05)`. The historical `ZEROMOM` correction remains in
place, so the final particle receives the velocity needed to make total
vertical momentum exactly zero.
