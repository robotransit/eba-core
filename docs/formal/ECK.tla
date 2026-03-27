------------------------------ MODULE ECK ------------------------------
(*
  Epistemic Control Kernel — Formal Model
  PlusCal / TLA+

  Models the propose/authorize/perform execution boundary.
  Verified properties (six state invariants + one temporal property):
      INV1  NoEffectWithoutGateAuthorization     (state invariant)
      INV2  NoEffectWithoutKernelAuthorization   (state invariant)
      INV3  NoEffectWithoutProposal              (state invariant)
      INV5  PolicyEscalationIsMonotonic          (state invariant)
      INV6  GateAuthorizationRequiresNonHalt     (state invariant)
      INV7  GateAuthorizationMatchesPermission   (state invariant)
      INV4  HaltFreezesKernelState               (temporal property — PROPERTY in TLC)

  Scope:
    - Policy mode state machine (NORMAL → GUIDED → ENFORCED → HALT)
    - propose/authorize/perform execution boundary
    - Two-gate authorization: gate check + kernel authorization
    - Halt as absorbing terminal state

  Deferred (out of scope for this spec):
    - Confidence signal dynamics (continuous-valued)
    - Drift monitor mechanics
    - Subtask generation and queue behaviour
    - ProposedAction provenance and whitelist content
    - Rate limiting

  Author: robotransit / virtuity.io
  Spec version: v0.3.0-pre
*)

EXTENDS Naturals, Sequences

\* ── Policy mode constants ───────────────────────────────────────────────────

CONSTANTS
    NORMAL,
    GUIDED,
    ENFORCED,
    HALT_MODE

\* Strict ordering for monotonic escalation (maps PolicyMode → rank)
PolicyOrder(m) ==
    IF m = NORMAL    THEN 0
    ELSE IF m = GUIDED   THEN 1
    ELSE IF m = ENFORCED THEN 2
    ELSE 3

PolicyModes == {NORMAL, GUIDED, ENFORCED, HALT_MODE}

\* ── Proposed action constants ────────────────────────────────────────────────

CONSTANTS
    NO_ACTION,   \* No proposal in flight
    PROPOSED     \* A structured proposal exists (content is abstract)

ActionStates == {NO_ACTION, PROPOSED}

(*--algorithm ECK

variables
    \* Current policy mode — monotonically escalates, never reverses
    policy_mode = NORMAL;

    \* Whether a structured ProposedAction is currently in flight
    proposed_action = NO_ACTION;

    \* Whether the policy gate has authorized execution for this cycle
    gate_authorized = FALSE;

    \* Whether the kernel has independently authorized this specific action
    kernel_authorized = FALSE;

    \* Whether execution_permitted has been set by the gate for this cycle
    execution_permitted = FALSE;

    \* Whether a real-world effect has been performed this cycle
    effect_performed = FALSE;

    \* Whether the agent is in the absorbing halt state
    halted = FALSE;

    \* Ghost variable: tracks policy_mode at the start of each step
    \* Used to verify monotonicity across transitions
    prior_policy_mode = NORMAL;

begin
    AgentLoop:
        while ~halted do

            \* ── Record prior mode for monotonicity check ─────────────────
            prior_policy_mode := policy_mode;

            \* ── Reset per-cycle state ─────────────────────────────────────
            proposed_action    := NO_ACTION;
            gate_authorized    := FALSE;
            kernel_authorized  := FALSE;
            execution_permitted := FALSE;
            effect_performed   := FALSE;

            \* ── Step 1: Policy escalation (irreversible, monotonic) ───────
            PolicyEscalation:
                either
                    \* No escalation this cycle
                    skip
                or
                    \* Escalate to GUIDED (only if currently NORMAL)
                    if policy_mode = NORMAL then
                        policy_mode := GUIDED
                    end if
                or
                    \* Escalate to ENFORCED (only if currently NORMAL or GUIDED)
                    if policy_mode = NORMAL \/ policy_mode = GUIDED then
                        policy_mode := ENFORCED
                    end if
                or
                    \* Escalate to HALT (from any non-halted mode)
                    policy_mode := HALT_MODE;
                    halted := TRUE
                end either;

            \* ── Check halt immediately after escalation ───────────────────
            HaltCheck:
                if halted then
                    goto Finished
                end if;

            \* ── Step 2: Propose execution ─────────────────────────────────
            \* LLM produces a structured ProposedAction.
            \* This is advisory only — no effects occur here.
            ProposeExecution:
                proposed_action := PROPOSED;

            \* ── Step 3: Gate check ────────────────────────────────────────
            \* Policy gate answers: "may execution occur at all?"
            \* Gate may only open when policy_mode ≠ HALT_MODE.
            \* INV6: gate_authorized => policy_mode ≠ HALT_MODE
            GateCheck:
                if policy_mode # HALT_MODE then
                    either
                        \* Gate opens — execution is permitted for this cycle
                        execution_permitted := TRUE;
                        gate_authorized     := TRUE
                    or
                        \* Gate refuses — no execution this cycle
                        skip
                    end either
                end if;

            \* ── Step 4: Kernel authorization ─────────────────────────────
            \* authorize_and_perform answers: "is this specific action
            \* within the authorized envelope?"
            \* Only reachable when gate_authorized = TRUE.
            \* INV1: effect_performed => gate_authorized
            \* INV2: effect_performed => kernel_authorized
            \* INV3: effect_performed => proposed_action = PROPOSED
            KernelAuthorize:
                if gate_authorized /\ proposed_action = PROPOSED then
                    either
                        \* Kernel authorizes this specific action
                        kernel_authorized := TRUE
                    or
                        \* Kernel refuses — action is outside authorized envelope
                        skip
                    end either
                end if;

            \* ── Step 5: Perform effect ────────────────────────────────────
            \* Real-world effect occurs ONLY when:
            \*   - gate_authorized = TRUE  (gate opened)
            \*   - kernel_authorized = TRUE (kernel approved the specific action)
            \*   - proposed_action = PROPOSED (a valid proposal exists)
            PerformEffect:
                if gate_authorized /\ kernel_authorized /\ proposed_action = PROPOSED then
                    effect_performed := TRUE
                end if;

        end while;

    Finished:
        skip

end algorithm; *)
\* BEGIN TRANSLATION (chksum(pcal) = "85790189" /\ chksum(tla) = "3dbd5beb")
VARIABLES policy_mode, proposed_action, gate_authorized, kernel_authorized, 
          execution_permitted, effect_performed, halted, prior_policy_mode, 
          pc

vars == << policy_mode, proposed_action, gate_authorized, kernel_authorized, 
           execution_permitted, effect_performed, halted, prior_policy_mode, 
           pc >>

Init == (* Global variables *)
        /\ policy_mode = NORMAL
        /\ proposed_action = NO_ACTION
        /\ gate_authorized = FALSE
        /\ kernel_authorized = FALSE
        /\ execution_permitted = FALSE
        /\ effect_performed = FALSE
        /\ halted = FALSE
        /\ prior_policy_mode = NORMAL
        /\ pc = "AgentLoop"

AgentLoop == /\ pc = "AgentLoop"
             /\ IF ~halted
                   THEN /\ prior_policy_mode' = policy_mode
                        /\ proposed_action' = NO_ACTION
                        /\ gate_authorized' = FALSE
                        /\ kernel_authorized' = FALSE
                        /\ execution_permitted' = FALSE
                        /\ effect_performed' = FALSE
                        /\ pc' = "PolicyEscalation"
                   ELSE /\ pc' = "Finished"
                        /\ UNCHANGED << proposed_action, gate_authorized, 
                                        kernel_authorized, execution_permitted, 
                                        effect_performed, prior_policy_mode >>
             /\ UNCHANGED << policy_mode, halted >>

PolicyEscalation == /\ pc = "PolicyEscalation"
                    /\ \/ /\ TRUE
                          /\ UNCHANGED <<policy_mode, halted>>
                       \/ /\ IF policy_mode = NORMAL
                                THEN /\ policy_mode' = GUIDED
                                ELSE /\ TRUE
                                     /\ UNCHANGED policy_mode
                          /\ UNCHANGED halted
                       \/ /\ IF policy_mode = NORMAL \/ policy_mode = GUIDED
                                THEN /\ policy_mode' = ENFORCED
                                ELSE /\ TRUE
                                     /\ UNCHANGED policy_mode
                          /\ UNCHANGED halted
                       \/ /\ policy_mode' = HALT_MODE
                          /\ halted' = TRUE
                    /\ pc' = "HaltCheck"
                    /\ UNCHANGED << proposed_action, gate_authorized, 
                                    kernel_authorized, execution_permitted, 
                                    effect_performed, prior_policy_mode >>

HaltCheck == /\ pc = "HaltCheck"
             /\ IF halted
                   THEN /\ pc' = "Finished"
                   ELSE /\ pc' = "ProposeExecution"
             /\ UNCHANGED << policy_mode, proposed_action, gate_authorized, 
                             kernel_authorized, execution_permitted, 
                             effect_performed, halted, prior_policy_mode >>

ProposeExecution == /\ pc = "ProposeExecution"
                    /\ proposed_action' = PROPOSED
                    /\ pc' = "GateCheck"
                    /\ UNCHANGED << policy_mode, gate_authorized, 
                                    kernel_authorized, execution_permitted, 
                                    effect_performed, halted, 
                                    prior_policy_mode >>

GateCheck == /\ pc = "GateCheck"
             /\ IF policy_mode # HALT_MODE
                   THEN /\ \/ /\ execution_permitted' = TRUE
                              /\ gate_authorized' = TRUE
                           \/ /\ TRUE
                              /\ UNCHANGED <<gate_authorized, execution_permitted>>
                   ELSE /\ TRUE
                        /\ UNCHANGED << gate_authorized, execution_permitted >>
             /\ pc' = "KernelAuthorize"
             /\ UNCHANGED << policy_mode, proposed_action, kernel_authorized, 
                             effect_performed, halted, prior_policy_mode >>

KernelAuthorize == /\ pc = "KernelAuthorize"
                   /\ IF gate_authorized /\ proposed_action = PROPOSED
                         THEN /\ \/ /\ kernel_authorized' = TRUE
                                 \/ /\ TRUE
                                    /\ UNCHANGED kernel_authorized
                         ELSE /\ TRUE
                              /\ UNCHANGED kernel_authorized
                   /\ pc' = "PerformEffect"
                   /\ UNCHANGED << policy_mode, proposed_action, 
                                   gate_authorized, execution_permitted, 
                                   effect_performed, halted, prior_policy_mode >>

PerformEffect == /\ pc = "PerformEffect"
                 /\ IF gate_authorized /\ kernel_authorized /\ proposed_action = PROPOSED
                       THEN /\ effect_performed' = TRUE
                       ELSE /\ TRUE
                            /\ UNCHANGED effect_performed
                 /\ pc' = "AgentLoop"
                 /\ UNCHANGED << policy_mode, proposed_action, gate_authorized, 
                                 kernel_authorized, execution_permitted, 
                                 halted, prior_policy_mode >>

Finished == /\ pc = "Finished"
            /\ TRUE
            /\ pc' = "Done"
            /\ UNCHANGED << policy_mode, proposed_action, gate_authorized, 
                            kernel_authorized, execution_permitted, 
                            effect_performed, halted, prior_policy_mode >>

(* Allow infinite stuttering to prevent deadlock on termination. *)
Terminating == pc = "Done" /\ UNCHANGED vars

Next == AgentLoop \/ PolicyEscalation \/ HaltCheck \/ ProposeExecution
           \/ GateCheck \/ KernelAuthorize \/ PerformEffect \/ Finished
           \/ Terminating

Spec == Init /\ [][Next]_vars

Termination == <>(pc = "Done")

\* END TRANSLATION 

\* ── TLA+ state invariants ───────────────────────────────────────────────────

\* INV1: No real-world effect without gate authorization
\* Checks gate_authorized directly — the variable the gate step sets.
\* GateAuthorizationMatchesPermission (INV7) separately asserts
\* gate_authorized = execution_permitted, keeping both variables in sync.
NoEffectWithoutGateAuthorization ==
    effect_performed => gate_authorized

\* INV2: No real-world effect without kernel authorization of the specific action
\* Checks kernel_authorized directly — the orthogonal second gate.
\* INV1 and INV2 together prove both authorization surfaces are required.
NoEffectWithoutKernelAuthorization ==
    effect_performed => kernel_authorized

\* INV3: No real-world effect without a valid proposal in flight
NoEffectWithoutProposal ==
    effect_performed => (proposed_action = PROPOSED)

\* INV5: Policy mode only advances in PolicyOrder, never reverses
PolicyEscalationIsMonotonic ==
    PolicyOrder(policy_mode) >= PolicyOrder(prior_policy_mode)

\* INV6: Gate authorization can only be granted when policy_mode ≠ HALT_MODE
GateAuthorizationRequiresNonHalt ==
    gate_authorized => (policy_mode # HALT_MODE)

\* INV7: gate_authorized and execution_permitted are synonymous
\* They are set together in GateCheck — this invariant makes that coupling
\* explicit and formal, preventing any future edit from setting one without
\* the other while passing all other invariants.
GateAuthorizationMatchesPermission ==
    gate_authorized = execution_permitted

\* ── Temporal property ───────────────────────────────────────────────────────

\* INV4: Halt freezes all kernel state variables.
\*
\* Once halted = TRUE, the seven operational variables stop changing.
\* `pc` (the PlusCal program counter) is intentionally excluded —
\* it is a translator artefact with no counterpart in the implementation.
\* In agent.py, step() simply returns False when halted; there is no
\* equivalent of pc advancing. The property proved here corresponds
\* exactly to what the implementation guarantees.
\*
\* Register as a PROPERTY in TLC (not an invariant — modal formula).
HaltFreezesKernelState ==
    [][halted => UNCHANGED <<policy_mode, proposed_action, gate_authorized,
                             kernel_authorized, execution_permitted,
                             effect_performed, prior_policy_mode>>]_vars

\* ── State invariant conjunction for TLC ─────────────────────────────────────
\*
\* Register ECKStateInvariants as an INVARIANT in TLC.
\* Register HaltFreezesKernelState separately as a PROPERTY in TLC.

ECKStateInvariants ==
    /\ NoEffectWithoutGateAuthorization
    /\ NoEffectWithoutKernelAuthorization
    /\ NoEffectWithoutProposal
    /\ PolicyEscalationIsMonotonic
    /\ GateAuthorizationRequiresNonHalt
    /\ GateAuthorizationMatchesPermission

=============================================================================
