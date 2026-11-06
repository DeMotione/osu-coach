# Star-Scale IRT (spec)

The experimental rating engine in `backend/src/osu_coach/domain/player/engines/irt/`. Below: first how osu! coach
differs from the proposal (the arena review's required fixes, and what review of the code settled), then the
proposal itself, unedited (Appendix A of the arena report).

## How osu! coach differs from the proposal

Built (the engine's states, fit and items):

1. **Tested-difficulty cap.** Per skill, the hardest difficulty held (`tested`) is the 95th percentile of the held
   items' difficulty, each weighted by its information at the fitted ability (`a²q(1−q)`), so a pile of easy notes
   doesn't pull it down. A fit above it shows as "at least `tested`" (state `untested`, no score, `at_least` =
   adapter(`tested`)). A skill whose items were all failed has no tested difficulty and shows no number.
2. **States.** `measured` (SE ≤ 0.35★), `provisional` (SE ≤ 0.75★, or two answers fit about as well),
   `untested`, `not_enough_data` (SE > 0.75★), `failed` (the solver didn't converge: no number, never a clamp).
3. **Farming.** A play weighs `recency × min(1, 3/N_setup, 5/N_set)`: one map/mod setup counts as at most 3 plays,
   one mapset (`beatmapset_id`, else the map MD5) as at most 5. Setups include the client, so stable and lazer
   plays of one map are separate setups.
4. **Solver.** numpy damped quasi-Newton (Levenberg–Marquardt on a BFGS-updated curvature, started from and
   reset to the exact finite-difference Hessian of the exact analytic gradient); a step is taken only if the log
   posterior rises; probabilities stay inside (1e-12, 1 − 1e-12);
   accuracy by bisection on its monotone score. No scipy needed.
5. **Several answers.** Four starts (every skill at L, L − 2, L + 2, and each skill at its items' median
   difficulty); converged answers within 2 log-posterior units but > 0.3★ apart widen the range to span them.
6. **Ranges.** SE² = D·Σ_kk + 0.25²/N_plays (play-to-play form) + ((θ(L+1) − θ(L−1))/2)² (how much the prior centre
   moves the answer). Constants are unfitted.
7. **Prior centre L.** The comfort level; else the provisional one; else the median star rating played; else 4★.
   The 0–100 scores are `clip(50 + 20·(θ − L), 0, 100)`.
8. **Accuracy.** Uses `head_result` and only plays that pass the DT accuracy gate (`timing_evidence_eligible`).
   At θ = b, 88% of single notes are 300s (`π_acc = 0.88`), not the proposal's 95%: real players' single notes are
   ~12% non-300 at their level (the Comfort-Based engine's reference), and with 95% every typical player's accuracy
   read 2–3★ below their level (score 0).
9. **Tap rule.** A stream note (S/D/F) judged 50 fails like a miss: class B (late) or T (early) by the sign of the
   hit error. The likelihood has one response per note, so a 50 is shared out over the note's skills like a
   miss of that class (reading and flow take a little of it too).
10. **Stamina.** D also takes stream notes 30 s or more into a dense tapping section (notes at most 200 ms apart;
    a 1 s gap would make nearly every note of a map "deep").
11. **Reading.** `b_read` adds `0.5·log2(max(1, visible notes / 4))`, so low AR on dense maps isn't "easy". The
    anchors were fitted without it, so a typical T★ map's `b_read` sits a little above T.
12. **Sliders.** Only sliders whose path leaves the follow circle (longer than one circle width) are items: a kick
    slider is held without moving, however fast. Slider speed is held at the anchor's top knot (13★) before the
    shape term: the pool knows maps' typical slider speeds, and single sliders of ordinary maps are far faster, so
    extrapolated they read 30★ and more. A player who never breaks sliders reads "at least" ~13–14★.
13. **Sessions.** A play's start is its replay time (saved at the end) minus its length.
14. **Consistency.** Kept from the Comfort-Based engine (combo and accuracy held from map to map).

Still to build (OPP and the rest of §4, §6.7, §15): OPP with an expanding bracket and no 13.5 bound (failure →
no number), OPP from `min(θ, tested)` and only with ≥ 4 measured/provisional skills; the same reading density
term on the equating rows; Train Next as the OPP gain of +0.5★, only for scored skills below OPP; pass chance and
expected misses from the fit; Progress and map displays.

Known limits: above about 8.5★ the reading and accuracy anchors are only the monotone steps (the pool has few
such maps), so DT players' reading and accuracy can read 12–15★.

---

# Star-Scale IRT

## 1. System name
**Star-Scale IRT**: a multidimensional item-response model. Every skill is a latent ability measured in stars, on the same scale as the difficulty of the notes the player hits or misses.

## 2. Core idea
Every note in every analysed replay is an *item*. It gets a difficulty for each skill it tests (aim, tapping, reading, ...), converted to star-equivalents by anchor curves that are fitted once on the bundled 4,968-map pool. The chance that skill k fails on a note is a logistic function of (θ_k − b_{i,k}). A note is hit only if no involved skill fails and no random lapse happens, and the app's re-simulated miss cause (aim / late-or-lost / early-or-no-tap) tells the model which skill most likely failed. The abilities θ_k, a lapse rate ε (consistency) and a fatigue shift δ are fitted together by maximum a posteriori (MAP) from the player's own hits and misses, with standard errors taken from the curvature of the posterior. Because θ and b share one absolute scale, "Aim 6.9★" means the same thing for every player: it is the aim difficulty at which this player loses 2% of notes to aim. That removes the "a 4★ and an 8★ player both have Aim 60" problem. OPP is the star level of the evenly skilled player who would handle the same share of pool maps as this player (test-characteristic-curve equating), so OPP is also in stars.

## 3. Skillsets

### 3.0 Shared measurement model
Every skill k ∈ {aim, flow, tap, stam, read, sl, acc} has an item class (the notes that test it), a per-note difficulty b_{i,k} in ★, a discrimination a_k (per ★) and an anchor probability π_k:

  q_k(θ, b) = 1 − σ(c_k + a_k·(θ − b)),  c_k = logit(π_k),  σ(z) = 1/(1 + e^{−z})   (M1)

q_k is the probability that skill k fails on the note. At θ_k = b it is 1 − π_k (2% for every skill, 5% non-300 for accuracy). Each ★ of margin multiplies the failure odds by e^{−a_k}. The anchor functions S_aim, S_spd, S_read, S_acc, S_sl (§6.1) turn a raw local demand into "the star rating of the median pool map with that demand".

**Item classes.** Only objects with `played = True` count, and spinners are excluded. A "head" is a circle or a slider head.

| Class | Rule (columns from `objects`) | Skills tested |
|---|---|---|
| J | head with run_len < 3 or run_pos = 0, and dist_norm ≥ 1 | aim, read |
| S | run_len ≥ 3, 1 ≤ run_pos < 16, dist_norm < 0.9 | tap, read |
| D | run_len ≥ 3, run_pos ≥ 16, dist_norm < 0.9 | stam, read |
| F | run_len ≥ 3, run_pos ≥ 1, dist_norm ≥ 0.9 (spaced stream) | flow, tap (stam if run_pos ≥ 16), read |
| SL | slider whose head was hit; response = `broke` | sl |
| AC | hit single note (run_len < 3, head hit); response = result ≠ 300 | acc |

Heads outside runs with dist_norm < 1 (stacks, overlaps) are left out: their demand is near zero, and the section-level aim_eq would mislabel them as hard.

**Miss classes.** A missed head is put in one class from `miss_reason`: **A** = aim (this includes speed_aim); **B** ("behind") = late or lost; **T** = early, no_tap, notelock, or a lazer `forced_miss`. Each skill gives off misses with a fixed class mix E_k = (E_{k,A}, E_{k,B}, E_{k,T}). These are prior constants, to be refitted (§11).

### 3.1 The skills

**Aim (θ_aim).** Hitting notes that need cursor travel: jumps and spaced singles. *Separate because* its misses are class A on notes with high aim_eq and low speed_eq; no other skill explains them. *Data:* J notes, per-object `aim_eq` (rosu-pp aim strain with the exact mods of the play, so CS/HR and DT are included), `miss_reason`. *Formula:* b_{i,aim} = S_aim(log₂ aim_eq_i), a_aim = 1.6, E_aim = (0.75, 0.25, 0). *Little data:* about 430 jump notes near the player's limit give SE 0.3★ (§9); far easier notes carry little information, so the estimate falls back toward the prior. *Failure cases:* aim_eq is a 400 ms section value, so an easy note in a hard section inherits the section's difficulty. Angle and "tech" aim are only as good as osu!'s strain model.

**Flow aim (θ_flow).** Aiming while tapping continuously: spaced streams. *Separate because* an F note tests flow and tap at once. Class-A misses on F notes go mostly to flow, and B/T misses go mostly to tap. *Data:* F notes. *Formula:* b_{i,flow} = S_aim(log₂ aim_eq_i), a_flow = 1.6, E_flow = (0.80, 0.20, 0). *Little data:* spaced streams are rare (7.5% of notes in the pool at 4.5–8★), so this skill is often "provisional". *Failure cases:* cut streams with a mixed spacing are split by the 0.9-diameter threshold.

**Tapping speed (θ_tap).** Finger speed on bursts and streams up to 16 notes. *Separate because* its misses are mostly B/T on notes where speed_eq, not aim_eq, is high. *Data:* S notes (and the tap part of F notes), `speed_eq`. *Formula:* b_{i,tap} = S_spd(log₂ speed_eq_i), a_tap = 2.0, E_tap = (0.10, 0.40, 0.50). *Little data:* about 280 stream notes near the limit give SE 0.3★. *Failure cases:* `speed_eq` does not tell 1/3 from 1/4 rhythms; rhythm complexity is folded into speed.

**Stamina (θ_stam).** Holding that speed past the 16th note of a run. *Separate because* players who are fine on bursts but "fall behind" deep in long streams are common, and this is exactly the weakness of the §7 player. *Data:* D notes. *Formula:* b_{i,stam} = S_spd(log₂ speed_eq_i), which uses the same anchor as tap, so θ_tap − θ_stam reads directly as "★ lost after 16 notes". a_stam = 2.0, E_stam = (0.05, 0.45, 0.50). *Little data:* runs longer than 16 notes are rare, so many players see "not enough data". *Failure cases:* minute-long stamina (marathons) is not a per-note quantity; the session parameter δ covers part of it.

**Reading (θ_read).** Reading approach rate, plus HD and FL. *Data:* every J/S/D/F note, meta `ar` (effective AR, already rate-adjusted), and the HD/FL flags. *Formula:* b_{i,read} = S_read(−log₂ preempt(AR_eff)) + h_HD·HD + h_FL·FL, with h_HD = 0.5★ and h_FL = 1.5★ (prior constants, fitted later), a_read = 1.2, E_read = (0.50, 0.20, 0.30). *Separate because* AR varies independently of aim_eq across plays (DT and HR raise AR on the same patterns), so misses that grow with AR at a fixed aim demand are identified as reading. *Failure cases:* b ignores note density and overlaps, and very low AR (AR 0 on dense maps) is treated as easy, which is a known gap (§14).

**Sliders (θ_sl).** Following fast or technical sliders. *Data:* SL items, `slider_vel_real`, `radius`, `slider_turn/corners/bends/vel_change`, `broke`. *Formula:* b_{i,sl} = S_sl(log₂(v_i·1000/(2r_i))) + κ_sl·log₂(shape_i·vchg_i), with κ_sl = 0.5★ per doubling. shape_i and vchg_i are the app's existing `slider_difficulty` factors (shape = 1 + 0.5·min(turn/π, 4) + 0.3·min(corners, 4) + 0.2·min(bends, 4); vchg = 1 + min(vel_change, 1)). a_sl = 1.0. *Failure cases:* lazer judges sliders more leniently (2.4× follow area), which needs the client offset γ (§8).

**Accuracy (θ_acc).** Timing precision. *Data:* AC items and the effective OD (with lazer, the window the judge actually used). *Formula:* b_{i,acc} = W_i + λ·(b_{i,loc} − W_i), with W_i = S_acc(−log₂ w300_i), w300_i = max(79.5 − 6·OD_eff, 1) ms of real time, b_{i,loc} = max(b_{i,aim}, b_{i,tap}), λ = 0.35 (a hard pattern also makes 300s harder), a_acc = 0.527, π_acc = 0.95. *Little data:* about 1,650 single notes give SE 0.3★, and almost every note is informative, because 300s are never certain. *Failure cases:* the OD cap at 10 for HR is respected through OD_eff, but HR's smaller CS does not enter b_acc.

**Two global parameters** are fitted with the skills and shown next to them:
- **Consistency (ε):** a per-note lapse probability that does not depend on difficulty, with class mix E_0 = (0.40, 0.30, 0.30) and prior Beta(2, 998). It is shown as "1 random miss per 1/ε notes" (uncapped, higher is better).
- **Session endurance (δ):** every θ_k except sl and acc is lowered by δ on notes flagged ℓ_i = 1 (played ≥ 40 min into a session, §6.3). The prior is N(0, 0.5²).

**Left out or merged.** Precision (small CS) is part of aim, because aim_eq already includes CS. speed_aim misses are class-A misses on run notes and are split between flow and tap by the mixture, not made a skill of their own. Tech aim, angle-specific aim and 1/3 finger control have no reliable per-note difficulty in rosu-pp, so they are future candidates (§13), not padding. The legacy "consistency" (chains and spread) becomes ε and δ. UR is shown only as a diagnostic: accuracy uses the judged 300/non-300 outcome, because that outcome is directly comparable to OD. Quadrant stays a playlist target. The skills really are separate: in the §7 fit the posterior correlations are aim–read −0.32, tap–flow −0.02 and tap–stam 0.01.

## 4. OPP (Overall Performance Points)
OPP answers this question: *"Which evenly skilled player handles the same share of real maps as you, near their own level?"* The answer is a star level.

**Equating set.** M = the 9,936 pool rows (4,968 maps × {NM, DT}), each with star rating s_m (`stars` or `stars_dt`). Per row: the pattern weights w_{aim,m} = jump_share + spaced_share, w_{flow,m} = spaced_stream_share, w_{stam,m} = min(stream_share, 8·long_runs/n_objects), w_{tap,m} = max(0, stream_share + burst_share − w_flow − w_stam), w_{read,m} = 1 and w_{sl,m} = slider_share. The component difficulties come from the anchors: B_{aim,m} = B_{flow,m} = S_aim(log₂(aim_m·r_m)), B_{tap,m} = B_{stam,m} = S_spd(log₂(speed_m·r_m)), B_{read,m} = S_read(−log₂(preempt(AR_m)/rate_m)), B_{sl,m} = S_sl(log₂(slider_velocity_m·rate_m·1000/diam_m)) (8 missing values get the median), and B_{acc,m} = W_m + λ(s_m − W_m) with W_m = S_acc(−log₂(max(79.5 − 6·OD_m, 1)/rate_m)). rate_m ∈ {1, 1.5}, and r_m = stars_dt/stars on DT rows (1 on NM rows), because the pool stores no DT aim/speed ratings.

**Map handling.** For a player (θ, ε):
- expected miss rate per note μ_m = ε + Σ_k w_{k,m}·q_k(θ_k, B_{k,m}), over k ∈ {aim, flow, tap, stam, read, sl};
- reference rate μ*_m = ε₀ + Σ_k w_{k,m}·(1 − π_k), with ε₀ = 0.002 (the miss rate of a player whose every θ equals the map's demands);
- non-300 rate e_m = q_acc(θ_acc, B_{acc,m}), with reference e* = 1 − π_acc = 0.05;
- Λ_m = 0.75·ln(μ_m/μ*_m) + 0.25·ln(e_m/e*), and h_m = σ(−Λ_m/τ_Λ) with τ_Λ = 0.25 (the soft "handled" indicator).

**Equating.** F(θ, ε; s) = mean of h_m over the rows with s − 0.5 ≤ s_m < s + 0.5. Then

  **OPP = the s ∈ [0.5, 13.5] with F(θ, ε; s) = F(s·𝟙, ε₀; s)**,

found by 50 bisection steps (F(θ) − F(s·𝟙) falls as s rises). 𝟙 is the evenly skilled player with θ_k = s for every k. By construction an evenly skilled player at s gets exactly OPP = s (checked: 3.000, 6.000, 9.000).

**Weights and why.** No hand-set weights. A skill counts as often as real maps at that star level test it (the pool's pattern shares), and the 0.75/0.25 split between misses and accuracy reflects that combo and pass decide a play more than 300s do (a prior choice, tested in §11). The *effective* weight of skill k is ∂OPP/∂θ_k. For the §7 player these are tap 0.241, sliders 0.200, read 0.187, aim 0.156, acc 0.125, stam 0.055 and flow 0.040, summing to 1.003.

**Why this beats a simple average.** (1) Rare patterns count less. Stamina appears in about 1% of pool notes, so a stamina hole should not cost as much as a tapping hole. (2) Miss rates add up, so a weak skill that is tested costs more than a strong skill earns ("weakest link"). A jump specialist (aim 7.5, read 7.6, tap 4.8, stam 4.2, …) gets OPP 6.02, below an evenly skilled 6★ player's 6.17, although their aim is 1.2★ higher. A plain mean would barely tell them apart (5.87 vs 6.03). (3) OPP sits on the same star scale as the skills, so "OPP 6.5, tap 6.2" is a meaningful comparison.

## 5. Scale decision
**Choice: an uncapped star scale.** No 0–100 and no percentile. θ_k, OPP and item difficulty are all star-equivalents. Above the last anchor knot (13★) the scale continues by linear extrapolation, so it has no ceiling. Each skill also gets a translation into natural units (BPM, diameters/s, AR, OD), and the relative view shows the signed gap θ_k − OPP.

- **Ceiling effects.** Nothing is clipped. The old "every top player is above 95%" failure cannot happen: a top player's accuracy simply lands at 9–10★ (OD 10.4+ windows under DT), and a 300 BPM streamer lands near 9.5★ tap. The ★ scale gets denser at the top (the anchors flatten), but it never saturates.
- **Beginners.** Stars are the one number every osu! player already knows from song select. "Aim 3.3★ ≈ jumps at 6.6 diameters/s" reads at once, and there is no "why am I 23/100" moment.
- **Comparing players.** The meaning is absolute. Two players with Aim 6.9★ lose 2% of their notes to aim on 6.9★-aim material, whatever their comfort level.
- **Comparing yourself over time.** The anchors are fixed per bundled-pool version, so a Progress row from March and one from November use the same ruler. Every stored value records `anchor_version`.
- **Meta changes or a star rework.** The anchors are medians over about 10k pool rows. Rebuilding the pool moves them only where the map population really shifted, and the cached group tables (§12) allow a full history refit in seconds. A rosu-pp rework changes aim_eq and speed_eq, so it needs an `ANALYSIS_VERSION` bump anyway. θ then stays "stars of the current calculator", just as players' own ★ numbers do.
- **Why not capped:** a cap re-creates the ceiling and needs a reference player. **Why not percentiles:** there is no population data at runtime.

**3★, 6★ and 9★ players** (typical illustrative profiles; OPP and translations computed with the §4 and §6.7 formulas):

| Player | aim | flow | tap | stam | read | sl | acc | ε (1 per) | **OPP** | mean θ | Translations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3★ | 3.3 | 2.7 | 3.1 | 2.8 | 3.5 | 3.0 | 2.9 | 0.004 (250) | **3.18** | 3.04 | aim 6.6 d/s, tap 137 BPM, stam 130 BPM, AR 8.00, sliders 5.2 d/s, OD 6.05 |
| 6★ | 6.3 | 5.9 | 6.0 | 5.6 | 6.5 | 5.8 | 6.1 | 0.002 (500) | **6.17** | 6.03 | aim 19.8 d/s, tap 196 BPM, stam 191 BPM, AR 9.60, sliders 8.2 d/s, OD 9.10 |
| 9★ | 9.6 | 9.0 | 9.2 | 8.7 | 9.8 | 8.8 | 9.3 | 0.0008 (1250) | **9.39** | 9.20 | aim 29.0 d/s, tap 287 BPM, stam 279 BPM, AR 10.66, sliders 11.7 d/s, OD 10.45 |
| jump-only 6★ | 7.5 | 5.6 | 4.8 | 4.2 | 7.6 | 5.4 | 6.0 | 0.002 (500) | **6.02** | 5.87 | aim 23.8 d/s, tap 180 BPM |

(d/s = circle diameters per second.)

## 6. Full formulas

### 6.1 Anchors S_k
Grid G = {1, 1.25, …, 13} (49 knots). Pool rows m as in §4, with diam_m = 2·(54.4 − 4.48·CS_m), preempt(AR) = 1200 − 150·(AR − 5) ms for AR ≥ 5 and 1200 + 120·(5 − AR) ms for AR < 5. Raw demands: u_aim = aim_m·r_m, u_spd = speed_m·r_m (rosu-pp ratings), u_read = −log₂(preempt(AR_m)/rate_m), u_acc = −log₂(max(79.5 − 6·OD_m, 1)/rate_m), u_sl = log₂(slider_velocity_m·rate_m·1000/diam_m).
1. κ_k(g) = median of u_k over the rows with g − 0.5 ≤ s_m < g + 0.5 (at least 15 rows, otherwise linear interpolation over g).
2. Monotone: κ_k(g_j) ← max(κ_k(g_j), κ_k(g_{j−1}) + 1/64).
3. X_k = log₂ κ_k for aim and spd, and X_k = κ_k for read, acc and sl.
4. S_k(u) = linear interpolation of g against X_k. Above X_k(13) it continues with slope (13 − 11)/(X_k(13) − X_k(11)), and below X_k(1) with slope (3 − 1)/(X_k(3) − X_k(1)).

Knots at whole stars (shown in natural units):

| ★ | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aim rating | 0.747 | 1.158 | 1.646 | 2.143 | 2.630 | 3.193 | 3.666 | 4.190 | 4.778 | 5.242 | 5.766 | 6.172 | 6.564 |
| speed rating | 0.477 | 0.779 | 1.246 | 1.713 | 2.127 | 2.567 | 3.063 | 3.399 | 3.878 | 4.414 | 4.886 | 5.325 | 5.961 |
| preempt ms | 1440 | 1200 | 880 | 700 | 580.8 | 525 | 489.7 | 400 | 366 | 348.5 | 333.7 | 319.6 | 306 |
| 300-window ms | 67.5 | 55.5 | 43.03 | 34.5 | 29.0 | 25.0 | 23.7 | 20.7 | 17.0 | 16.28 | 15.59 | 14.93 | 14.30 |
| slider d/s | 1.99 | 3.50 | 5.21 | 6.31 | 7.42 | 8.34 | 9.93 | 11.10 | 11.82 | 12.95 | 14.39 | 15.69 | 16.45 |

Examples: S_aim(log₂ 3.0) = 5.66★ and S_spd(log₂ 2.5) = 5.85★. AR 9.3 → 5.50★, AR 10 → 7.75★, AR 10.33 → 8.00★.

### 6.2 Item difficulties
These are the per-class formulas of §3.1:
- b_aim = b_flow = S_aim(log₂ aim_eq_i);
- b_tap = b_stam = S_spd(log₂ speed_eq_i);
- b_read = S_read(−log₂ preempt(AR_eff)) + 0.5·HD + 1.5·FL;
- b_sl = S_sl(log₂(1000·v_i/(2r_i))) + 0.5·log₂(shape_i·vchg_i) + γ·lazer_i, with γ = 0 until it is fitted (§11);
- b_acc = W_i + 0.35·(max(b_aim, b_tap) − W_i).

aim_eq and speed_eq are the existing per-object columns (rosu-pp with the play's mods).

### 6.3 Weights, sessions, grouping
- **Note weight:** ω_i = ω_r·ω_cfg. ω_r = 1 if the replay is ≤ 180 days older than the newest one, otherwise 0.5^((age − 180)/90). ω_cfg = min(1, 3/N_cfg), where N_cfg counts the plays of that configuration (map_md5:mods@rate).
- **Session:** a chain of replays with gaps < 20 min. ℓ_i = 1 if the replay started ≥ 40 min after its session's first replay.
- **Exclusions:** stable replays with `sim_agreement` < 0.97, and lazer replays whose simulated counts do not match.
- **Group key** = (class, client, ℓ, every b_{i,k} rounded to 0.05★). Per group: n_g = Σ ω_i and f_{g,c} = Σ ω_i over the misses of class c (for SL groups: over the breaks).

### 6.4 Likelihood and posterior
For a head group g with skill set K_g, q_{g,k} = q_k(θ_k − δ·ℓ_g, b_{g,k}). Then

  p_g = (1 − ε)·Π_{k∈K_g}(1 − q_{g,k})
  ρ_{g,c} = (ε·E_{0,c} + Σ_k q_{g,k}·E_{k,c}) / (ε + Σ_k q_{g,k})
  ln L_g = (n_g − Σ_c f_{g,c})·ln p_g + Σ_{c∈{A,B,T}} f_{g,c}·ln((1 − p_g)·ρ_{g,c})

For an SL group: ln L_g = (n_g − f_g)·ln p_g + f_g·ln(1 − p_g), with p_g = (1 − ε)(1 − q_{g,sl}).

With φ = (θ_aim, θ_flow, θ_tap, θ_stam, θ_read, θ_sl, δ, η = logit ε), the log posterior (up to constants) is

  ℓ(φ) = Σ_g ln L_g − Σ_k (θ_k − L)²/(2τ²) − δ²/(2·0.5²) + (α − 1)·ln ε + (β − 1)·ln(1 − ε)

with L = comfort stars (`ratings.comfort`, the prior centre), τ = 1.5, α = 2 and β = 998.

Accuracy is fitted separately: ℓ_acc = Σ_g [f_g·ln q_g + (n_g − f_g)·ln(1 − q_g)] − (θ_acc − L)²/(2τ²), with q_g = q_acc(θ_acc, b_g).

Constants: a = (aim 1.6, flow 1.6, tap 2.0, stam 2.0, read 1.2, sl 1.0, acc 0.527); c_k = logit 0.98 = 3.8918 (acc: logit 0.95 = 2.9444). The class mixes E_{k,·} are as in §3.1, and E_{0} = (0.40, 0.30, 0.30).

### 6.5 Fitting
Newton–Raphson on φ from (L, …, L, 0, logit 0.002): φ ← φ − t·H⁻¹∇ℓ, halving t until ℓ does not decrease (t ≥ 10⁻⁴), and stopping when max|t·step| < 10⁻⁶. In production the gradient and Hessian are analytic; the reference script uses central differences with h = 10⁻⁴. Accuracy uses 1-D Newton.

### 6.6 Standard errors
Σ = (−∇²ℓ(φ̂))⁻¹ and SE_k = √(D·Σ_kk), with design effect D = 2, because notes within a replay are not independent. SE_acc = √(D/I_acc), I_acc = 1/τ² + Σ_g a_acc²·n_g·q_g(1 − q_g). SE_OPP = √(gᵀ·Σ_θ·g), where g_k = ∂OPP/∂θ_k by central differences of ±0.05, and Σ_θ is Σ·D for the six skills plus SE_acc² (ε and δ are held fixed).

### 6.7 Translations, relative view, predictions
- **Translation** T_k(θ) uses the same grid, median and monotone rule on physical demands: jump_velocity·rate·1000/diam (aim, d/s), max(stream_bpm, burst_bpm)·rate (tap and stam, BPM), slider velocity in d/s (sl), preempt → AR = 5 + (1200 − p)/150, and w300 → OD = (79.5 − w)/6. It means "the median pool map at θ★ has this demand" (in absolute units, these are the app's `demand.py` curves).
- **Relative view:** r_k = θ_k − OPP (★). Only for 0–100 consumers during migration: clip(50 + 20·r_k, 0, 100).
- **Expected misses on any target map or section** = Σ_i [1 − (1 − ε)·Π_k(1 − q_k(θ_k, b_{i,k}))].

## 7. Worked example
**Inputs (invented, realistic).** L = 6.2 (comfort). 300 replays, all ≤ 4 months old (so ω_r = 1), no configuration played more than 3 times (ω_cfg = 1), and 40 lazer replays (no lazer slider offset, γ = 0). DT rows appear as AR 10.33/10.5 and OD 9.75/10.42; the HR row is OD 10. The counts below come from a seeded simulation of the described player (hidden true values: aim 6.9, flow 6.4, tap 6.2, stam 5.3, read 7.4, sl 5.6, acc 6.5, ε 0.0015, δ 0.35), so they hang together; the fit does not see the true values. About 111k head notes, 40k slider bodies and 46k single notes for accuracy (≈ 505 objects per replay).

**Head and slider groups** (f = misses by class A/B/T; for L rows, f_A = slider breaks):

| id | class | ℓ | n | b (★) | f_A | f_B | f_T |
|---|---|---|---|---|---|---|---|
| J1 | J | 0 | 30000 | aim 3.50, read 4.25 (AR 9.0) | 24 | 14 | 17 |
| J2 | J | 0 | 22000 | aim 5.00, read 5.50 (AR 9.3) | 45 | 19 | 26 |
| J3 | J | 0 | 9000 | aim 6.00, read 5.50 (AR 9.3) | 45 | 18 | 8 |
| J4 | J | 0 | 4000 | aim 6.60, read 6.00 (AR 9.5) | 51 | 15 | 4 |
| J5 | J | 0 | 1500 | aim 7.20, read 6.00 (AR 9.5) | 44 | 14 | 2 |
| J6 | J | 0 | 400 | aim 7.80, read 6.50 (AR 9.6) | 18 | 4 | 0 |
| J7 | J | 0 | 2500 | aim 6.40, read 7.75 (AR 10.0) | 63 | 23 | 25 |
| J8 | J | 0 | 2000 | aim 6.30, read 8.00 (AR 10.33, DT) | 59 | 27 | 29 |
| J9 | J | 0 | 800 | aim 6.60, read 8.54 (AR 10.5, DT) | 39 | 12 | 13 |
| J10 | J | 1 | 2500 | aim 6.00, read 5.50 (AR 9.3) | 22 | 4 | 3 |
| S1 | S | 0 | 12000 | tap 4.00, read 4.25 | 7 | 9 | 8 |
| S2 | S | 0 | 7000 | tap 5.00, read 5.50 | 15 | 18 | 18 |
| S3 | S | 0 | 3500 | tap 5.60, read 5.50 | 9 | 12 | 13 |
| S4 | S | 0 | 1500 | tap 6.20, read 6.00 | 7 | 12 | 18 |
| S5 | S | 0 | 500 | tap 6.80, read 6.00 | 2 | 10 | 11 |
| S6 | S | 0 | 600 | tap 6.40, read 8.00 | 11 | 14 | 27 |
| S7 | S | 1 | 1000 | tap 5.60, read 5.50 | 3 | 10 | 8 |
| D1 | D | 0 | 1500 | stam 4.50, read 4.25 | 2 | 5 | 1 |
| D2 | D | 0 | 1000 | stam 5.30, read 5.50 | 2 | 8 | 16 |
| D3 | D | 0 | 500 | stam 5.90, read 6.00 | 1 | 19 | 16 |
| F1 | F | 0 | 4000 | flow 5.00, tap 4.50, read 5.50 | 9 | 5 | 9 |
| F2 | F | 0 | 2500 | flow 6.00, tap 5.00, read 5.50 | 28 | 7 | 4 |
| F3 | F | 0 | 800 | flow 6.60, tap 5.30, read 6.00 | 15 | 4 | 3 |
| L1–L6 | SL | 0 | 20000 / 12000 / 5000 / 2000 / 800 / 250 | sl 3.0 / 4.5 / 5.5 / 6.3 / 7.0 / 7.8 | 62 / 116 / 111 / 74 / 63 / 36 | – | – |

(Tap b on S rows 4.0–6.8 ≈ 150–230 BPM 1/4; S6 is DT.)

**Accuracy groups** (W = S_acc(−log₂ w300), b = W + 0.35(b_loc − W)):

| id | OD_eff | w300 ms | W | b_loc | b | n | non-300 |
|---|---|---|---|---|---|---|---|
| A1 | 8.0 | 31.5 | 4.25 | 3.5 | 3.987 | 9000 | 127 |
| A2 | 8.5 | 28.5 | 5.25 | 5.0 | 5.162 | 12000 | 289 |
| A3 | 9.0 | 25.5 | 5.75 | 6.0 | 5.838 | 14000 | 493 |
| A4 | 9.3 | 23.7 | 7.00 | 6.3 | 6.755 | 6000 | 351 |
| A5 (HR) | 10.0 | 19.5 | 8.25 | 6.0 | 7.463 | 2500 | 196 |
| A6 (DT) | 9.75 | 21.0 | 7.75 | 6.3 | 7.242 | 1500 | 93 |
| A7 (DT) | 10.42 | 16.98 | 9.03 | 6.6 | 8.178 | 1200 | 152 |

**Step 1: MAP fit (§6.5).** Newton converges in 8 iterations (max|∇ℓ| = 3.6·10⁻⁸, ℓ = −8616.102 without constants):

| θ_aim | θ_flow | θ_tap | θ_stam | θ_read | θ_sl | θ_acc | δ | ε |
|---|---|---|---|---|---|---|---|---|
| 6.947 ± 0.079 | 6.528 ± 0.152 | 6.186 ± 0.078 | 5.264 ± 0.096 | 7.326 ± 0.083 | 5.534 ± 0.079 | 6.516 ± 0.067 | 0.376 ± 0.139 | 0.00132 (1 per 758; SE of logit 0.189) |

The posterior correlations are small (aim–read −0.32, tap–flow −0.02, tap–stam 0.01). Every estimate is within 1.3 SE of the hidden truth.

**Step 2: check one group by hand (J8, DT, AR 10.33).**
- q_aim = 1 − σ(3.8918 + 1.6·(6.947 − 6.30)) = 1 − σ(4.927) = 0.00719.
- q_read = 1 − σ(3.8918 + 1.2·(7.326 − 8.00)) = 1 − σ(3.083) = 0.04381.
- p = 0.99868 × 0.99281 × 0.95619 = 0.94806, so the model expects 2000 × 0.05194 = 103.9 misses; 115 were observed.
- Responsibilities for class A: aim 0.194, read 0.787, lapse 0.019 (for example aim = 0.75·q_aim/(0.4ε + 0.75q_aim + 0.5q_read) = 0.005393/0.027826). For class B: aim 0.164, read 0.800. For class T: read 0.971.

So the DT misses are read as a *reading* problem, not an aim problem, which matches "struggles at AR 10.3+".

**Step 3: accuracy check (A3).** q = 1 − σ(2.9444 + 0.527·(6.516 − 5.838)) = 1 − σ(3.302) = 0.0355, which predicts 497 non-300s against 493 observed. Overall the non-300 share is 3.68%, ≈ 97.5% accuracy.

**Step 4: OPP (§4).** Bisection gives **OPP = 6.510 ± 0.032**, with F(θ, ε; 6.51) = 0.310 (the share of 6.0–7.0★ pool rows "handled"). The simple mean of the seven θ is 6.329. Effective weights ∂OPP/∂θ: tap 0.241, sl 0.200, read 0.187, aim 0.156, acc 0.125, stam 0.055, flow 0.040.

**Step 5: translations (§6.7).** Aim 22.0 d/s, tap 199 BPM, stamina 187 BPM, reading AR 9.81, sliders 7.9 d/s, accuracy OD 9.18.

**Step 6: prediction.** On a 300-note section with 7.0★ aim at AR 10 (b_read 7.75): per note 1 − (1 − ε)(1 − q_aim)(1 − q_read) = 0.0551, so about 16.5 misses.

**Output the player sees:** OPP **6.51★**. Aim 6.95★ (strong), reading 7.33★, flow 6.53★, accuracy 6.52★, tap 6.19★, sliders 5.53★, stamina 5.26★ (−0.93★ after 16 notes), consistency 1 random miss per 758 notes, session endurance −0.38★ after 40 min. All of the brief's traits come back out: strong jumps, weak long streams (B/T misses on D rows), the AR 10.3 reading wall, slider breaks at high SV, and the end-of-session drop.

## 8. Why it represents real skill
The model is a generative account of what really happened: which notes were hit, which were missed, and how they were missed. Its difficulties come from osu!'s own strain model, evaluated with the exact mods of each play. Skill is then the difficulty the player can handle, in the same units. There is no comfort-relative "expected" value anywhere in the measurement.

- **Difficulty.** No comfort weighting is needed. A note's information is a_k²·q(1 − q): it peaks near the player's limit and fades on easy notes (aim: 0.050 per note at margin 0, 0.00043 at margin 3★). Hard maps count for more automatically, but only to the extent that they are informative.
- **Mods.** DT, HT and custom rates enter through the rosu-pp strains (aim_eq and speed_eq with the mods) and through real-time preempt and 300-windows. HR and EZ enter through CS (in aim_eq) and the effective AR and OD. The anchors contain NM and DT rows, so a DT-heavy player is on the same ruler. HD and FL add +0.5★ and +1.5★ to reading difficulty only, and they help only if the notes are actually hit.
- **Map length.** Every note is one item, so a long map gives more evidence but no bonus. Session fatigue goes into δ instead of lowering every θ. Fatigue within one map is not modelled (§14).
- **Luck.** A lucky FC is a few hundred hits among ~10⁵ items. It moves θ by roughly its information share, not by "best play" logic.
- **Farm maps.** A farm map's notes count, but only for the skills it tests. OPP equating then punishes imbalance (§4, §10).
- **Small samples.** The prior N(L, 1.5²) plus the SE-based display states (§9) keep the numbers honest.
- **Old replays.** ω_r halves the weight every 90 days beyond 180 days. Progress refits each period on its own replays, which shows form against peak.
- **Stable vs lazer.** Both are judged by the app's faithful re-simulation, with identical response definitions. The 300-window is the one each judge actually used (lazer's −0.5 ms flooring included). Client is part of the group key, so the slider-leniency offset γ can be fitted from players who use both clients (§11).

## 9. Uncertainty
- **Computation:** SE from the posterior curvature with design effect D = 2 (§6.6). OPP gets its SE by the delta method; ε gets an SE on the logit scale.
- **Display states** per skill:
  - **measured:** SE ≤ 0.35★, shown as θ with a 90% range θ ± 1.645·SE;
  - **provisional:** 0.35 < SE ≤ 0.75★, shown greyed with its range;
  - **not enough data:** SE > 0.75★. Only the bound "≥ θ̂ − 1.645·SE" is shown, plus a hint ("play maps with aim around X★"). With no data, SE = τ·√D = 2.12★.
- **OPP** is shown when at least 4 of the 7 skills are measured or provisional; otherwise it is marked provisional.
- **Minimum data.** Notes needed for SE = 0.3★ (with D = 2) at margin θ − b:

| margin θ − b | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| aim (J notes) | 434 | 2,082 | 10,243 | 50,667 |
| tap / stam (S/D notes) | 278 | 1,982 | 14,576 | 107,637 |
| accuracy (single notes) | 1,651 | 2,683 | 4,433 | 7,398 |

This turns the old "untested" rule into numbers. A player who only clears material 3★ below their limit is simply *not measured yet*, and the app says which difficulty to play to get measured. A typical 15-replay sample (~7,500 heads, mostly within ±1★ of the limit) measures aim, tap, reading and accuracy at SE ≈ 0.3–0.45. Stamina and flow usually stay "not enough data" until long or spaced streams have been played.
- **Model-fit check:** per class and pattern, the observed misses are compared with the expected misses (the J8 check in §7, 115 vs 103.9). A deviation above 3 SD flags the skill as "uncertain model fit".

## 10. Anti-abuse
- **Spamming easy maps.** Notes 3★ below the limit carry about 1/117 of the information of notes at the limit (aim). The likelihood is flat above b + 2, so θ cannot rise past what was actually tested; it stays near the prior with a large SE and shows "not enough data". The prior centre L comes from *clean* plays, so missing on purpose on hard maps cannot move it up either.
- **Farming one map type.** Only that skill rises. OPP weights skills by how often real maps at that level test them, and miss rates add up, so the jump-only profile (aim 7.5★) gets OPP 6.02, below the evenly skilled 6★ player's 6.17.
- **Replaying one map.** ω_cfg = min(1, 3/N_cfg) caps one configuration at three plays' worth, which limits memorisation gains.
- **One mod only (DT/HR/HD/FL).** There are no mod multipliers. Difficulty is what rosu-pp and the windows say, the anchors include DT rows, and the HD/FL adders affect reading only and pay off only through hits. A player whose HD plays don't miss more simply gains reading θ, which is correct.
- **Simulation or judge artefacts.** Replays with sim_agreement < 0.97 or lazer count mismatches are excluded.
- **Not covered:** deleting or quitting bad attempts (no replay is left) inflates θ near the top of what a player attempts (§14). Failed lazer replays are used when they exist.

## 11. Validation plan
All constants marked "prior" (a_k, E_k, h_HD, h_FL, κ_sl, λ, γ, D, τ_Λ and the 0.75/0.25 split) are fitted after implementation by the steps below. π_k = 0.98 stays fixed, because it *defines* the scale.
1. **Parameter recovery.** Simulate 200 synthetic players from §6.4, as in §7. Required: bias < 0.1★ and 90%-interval coverage of 85–95%.
2. **Split-half reliability.** Split each real profile (test fixtures plus volunteer libraries) by configuration into two halves. Required: corr(θ̂₁, θ̂₂) ≥ 0.9 for measured skills. The standardised differences (θ̂₁ − θ̂₂)/√(SE₁² + SE₂²) must have variance 1, and this is how D is fitted.
3. **Held-out prediction.** Predict misses by class and pattern on each player's newest 20% of replays. Required: a better log score than `misses.fit_miss_model`, and a calibration slope of 0.9–1.1. E_k, a_k and λ are fitted by maximising this marginal likelihood across players.
4. **Reference replays (39).** Each top-player group must get θ ≥ 9★ on its featured skill, or a lower bound ≥ 9★ when the plays are FCs, and the 300 BPM DT stream group must get tap ≥ 9.3★. No reference group may show "not enough data" for accuracy.
5. **Rank monotonicity.** Use an offline test corpus of public top-50 replays from players near ranks 100, 1k, 10k, 100k and 500k. Required: Spearman(OPP, −log rank) ≥ 0.8, and OPP monotone across the rank bands.
6. **Invariance.** For players with both NM and DT plays (and both stable and lazer), fit each part separately. Required: |Δθ| ≤ 2·SE. This fits h_HD, h_FL and γ.
7. **Real improvement.** For volunteers with months of history, monthly θ must rise along with their own pp history, and a jump larger than 2·√(SE₁² + SE₂²) is flagged as real.
8. **Unit tests.** The §7 group table is a fixture: the fit must reproduce the MAP to 10⁻³, F-equating must give OPP(s·𝟙) = s, and θ must increase when misses are removed.

## 12. Performance
- **Per replay:** one vectorised pass over `objects` (~1,000 rows): class masks, `np.interp` for the b's, and a groupby. This takes about 5–10 ms and gives a group table of about 300 rows × 12 columns (≈ 15 KB), cached as `<data dir>/irt/<analysis key>-irt<IRT_VERSION>-a<anchor_version>.npz`. It only uses existing columns (aim_eq, speed_eq, run_len/run_pos, dist_norm, miss_reason, result, the slider columns, ar/od, mods), so **no `ANALYSIS_VERSION` bump** is needed.
- **Merge:** the weights ω_r·ω_cfg are applied at merge time (they depend on the newest replay and on play counts), then the groups are summed by key. This gives about 5k–20k groups even for 10,000 replays.
- **Fit:** Newton with an analytic gradient and Hessian is O(G·|K_g|) per iteration, about 8 iterations, i.e. ~10–30 ms in numpy. Memory is a few MB.
- **OPP:** each F evaluation touches about 1,000 pool rows in the ±0.5★ window. The evenly-skilled side F(s·𝟙; s) does not depend on the player, so it is tabulated once per anchor version. 50 bisection steps take ≈ 30 ms, and the SE needs 14 more solves (< 0.5 s; cached by θ).
- **Incremental update:** a new replay's group table is added to the merged counts, and Newton is warm-started from the previous φ̂ (2–3 iterations). That is < 0.2 s, against the current full `build_profile` (21 s at 200 replays, still run for other pages).
- **Progress:** a period is the sum of its replays' group tables, so each period fit takes ~20 ms. Hundreds of periods take a few seconds, with no `build_profile` call per period for skills. This removes the heaviest recurring compute.
- **Repo fit:**
  - Pure `profile/domain/irt.py`: `group_table`, `merge`, `fit`, `standard_errors`, `opp`, `translate`, `expected_misses`.
  - Generated `profile/domain/irt_tables.py` (49-knot anchors and translations, constants), made by `backend/tools/build_irt_tables.py` from the pool, with a staleness test like `test_demand.py`.
  - The equating set (9,936 × 13 float32 ≈ 0.5 MB) ships as `profile/data/irt_equating.npz`. `profile/service.py` loads it and passes it in, because profile may not import `maps`.
  - `build_profile` adds `Profile.skill_abilities` {k: θ, se, state, translation, n_items}, followed by schemas and an OpenAPI regeneration.
  - `progress` stores `irt_<k>`, `irt_<k>_se`, `irt_opp` and `anchor_version` in `month_metrics`.
  - `readiness.py` uses `expected_misses`, and goals use `score_source = "irt"` with targets in ★.

## 13. Flexibility
- **Adding a skill** means adding an item class, a b formula, a_k and an E row; the likelihood is generic over K_g. Example: "sharp-angle aim" as J notes with angle < 60°, using the same anchor and weighted by the pool's `sharp_share` in OPP.
- **Changing weights:** OPP has no hand-set skill weights, only the misses/accuracy split (0.75/0.25) and τ_Λ. Rebuilding the pool updates the pattern frequencies automatically, so a meta shift changes OPP weights by data, not by opinion.
- **New mods:** anything rosu-pp rates goes into b automatically. A mod with no geometric effect gets one fitted additive term on the skill it affects (as HD/FL do on reading).
- **pp or star rework:** bump `ANALYSIS_VERSION` (new strains), rebuild the anchors from the recomputed pool, and refit the history from the caches. `anchor_version` separates the eras in Progress.
- **Better difficulty inputs:** when rosu-pp exposes reading or flashlight strains again, b_read becomes S_read(reading_eq), a one-line change. Per-note strains would replace the section values without touching the model.
- **Later:** a hierarchical population prior (bundled) can replace N(L, τ²) without changing the API.

## 14. Advantages and downsides
**Advantages**
1. Absolute and readable. Skills, OPP and maps share one ★ scale, and the same model predicts misses on any map (readiness and recommendations come for free).
2. Uses every note, weighted by its information. The old "untested" problem becomes a quantified uncertainty with a concrete "play this to be measured" hint.
3. Miss causes separate the skills. Misses on DT jumps are correctly assigned to reading rather than aim (J8: 79% reading).
4. No hand-set OPP weights. The weakest-link behaviour and the pool frequencies decide.
5. Cheap and incremental, and it makes Progress much faster.

**Downsides (honest)**
1. **Difficulty quality is capped by the inputs.** aim_eq and speed_eq are 400 ms section values built with a heuristic constant, not per-note difficulties, so an easy note in a hard section is mislabelled. DT rows of the anchor use aim·stars_dt/stars (the pool has no DT aim rating), and there are no HR rows.
2. **Many constants are priors until fitted** (a_k, E_k, λ, κ_sl, h_HD, h_FL, γ, τ_Λ, 0.75/0.25). The a_k set how far θ moves per observed miss rate, so before fitting, absolute values may be off by a few tenths of a star.
3. **Local independence is violated** (warm-up, memorisation, streaks inside a play). D = 2 is a guess, and SEs may be optimistic until step 11.2 fits D.
4. **Selection bias.** Failed or quit plays leave no replay, so θ is overestimated near the top of what a player attempts.
5. **The prior is centred on comfort L.** With little data θ is pulled toward L, which is a level-relative anchor. The state labels hide this for "not enough data", but provisional values are partly relative.
6. **Coverage gaps.** Reading ignores density and treats very low AR as easy. Stamina is per run, not per minute. Fatigue inside one map is not modelled. Accuracy ignores HR's smaller CS and the UR shape.
7. **Weak identification.** It can happen when patterns are confounded; for example, a DT-only player's AR and aim demand rise together. The SEs and the aim–read correlation show this, but the user just sees wider ranges.
8. **Learning curve.** "θ = where you lose 2% of notes to this skill" must be explained. A ★ number looks familiar but does not mean "I can FC maps of this rating": the §7 player handles only 31% of pool rows at 6.0–7.0★ in the soft sense of §4.
9. **Migration cost.** Goals, readiness, the map recommender and the stored Progress rows assume 0–100. An adapter (§6.7) bridges them during the switch.

## 15. Usability
- **Headline:** "**OPP 6.51★** (± 0.03): you handle maps like an all-round 6.5★ player." Comfort level L is shown next to it.
- **Skill ladder (the main chart):** one horizontal ★ axis (ECharts). Each skill is a dot with its 90% bar, and vertical lines mark OPP and L. Dots left of OPP are weaknesses, dots right of it are strengths (the relative view r_k). On hover: "Tap 6.19★ ≈ 199 BPM streams at 98% per note". Chips: "1 random miss per 758 notes", "−0.38★ after 40 min".
- **Train next (one number):** the OPP gain from +0.5★ in each skill (≈ 0.5·∂OPP/∂θ_k). For the §7 player: **tap +0.12**, sliders +0.10, reading +0.09, aim +0.08, accuracy +0.06, stamina +0.03, flow +0.02. That gives "Train next: streams. Practise maps with tap 6.2–6.7★ (≈ 200–215 BPM)". The recommender picks pool maps with B_tap ∈ [θ_tap, θ_tap + 0.5], where the player hits about 96–98% of the relevant notes: hard but productive. Stamina ranks low because long streams are rare in ranked maps; on stream maps it shows up in the per-map view instead.
- **Per-map readiness:** "On this map: ~16 misses expected, 70% from reading at AR 10.3." This is the expected-misses formula split by skill responsibility.
- **Progress:** θ per month with SE bands, and changes beyond 2σ are marked "real improvement".
- **Beginners** see the same language at 3★ ("Aim 3.3★ ≈ 6.6 diameters/s"). Low-data skills say exactly what to play to get measured.

