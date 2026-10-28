import Lean
open Lean Meta

theorem good {α β γ : Type} {f : α → β} {g : β → γ}
    (hg : Function.Injective g) (hf : Function.Injective f) :
    Function.Injective (g ∘ f) :=
  fun x y h0 => @hf x y (@hg (f x) (f y) h0)

-- Submit a deliberately incorrect core expression directly to the kernel.
-- This bypasses the elaborator's ordinary rejection of ill-typed source.
run_meta do
  let ci ← getConstInfo ``good
  let bad ← lambdaTelescope (ci.value! (allowOpaque := true)) fun xs _ =>
    mkLambdaFVars xs (mkApp3 xs[6]! xs[7]! xs[8]! xs[9]!)
  try
    addDecl (.thmDecl {
      name := `inj_comp_bad
      levelParams := ci.levelParams
      type := ci.type
      value := bad
    })
    logInfo "UNEXPECTED ACCEPTANCE"
  catch ex =>
    logInfo m!"EXPECTED KERNEL REJECTION:\n{ex.toMessageData}"
