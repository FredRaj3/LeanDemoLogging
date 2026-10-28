import Lean
open Lean Meta

/-! # How the kernel checks a proof-/

/-! ## 1. The proof
`diagnostics` lists the definitions the kernel unfolded while checking it. -/

/- An arbitrary function i between two generic types A and B -/
variable {A B : Type} (i : A → B)

/-Function.Injective takes in two types (inferred by Lean), a function between the
two types, and outputs a Prop -/
#check Function.Injective

/-The term of type Prop that Function.Injective outputs. A proof that a function
is injective means constructing a term of this type. -/
#print Function.Injective

/- The type of Function.Injective applied to the function i (this should be Prop)-/
#check Function.Injective i

/- Reduce the type of Function.Injective i so we can see how it is constructed -/
#reduce (types := true) Function.Injective i


/- A proof that the function i is Injective -/
variable (ii : Function.Injective i)

/- ii has type Function.Injective i, so it is a proof of the proposition
 ∀ ⦃a₁ a₂ : A⦄, i a₁ = i a₂ → a₁ = a₂ -/
#check ii


#check Function.comp

/- The main theorem with the proof term from the slides

Note  the diagnostics:
the elaborator unfolded Function.injective 7 times
the kernel unfolded Function.Injective 3 times and Function.comp 2 times
-/
set_option diagnostics true in
set_option diagnostics.threshold 0 in
theorem inj_comp {α β γ : Type} {f : α → β} {g : β → γ}
    (hg : Function.Injective g) (hf : Function.Injective f) :
    Function.Injective (g ∘ f) :=
  fun x y h0 =>
    let h1 : f x = f y := @hg (f x) (f y) h0
    let h2 : x = y := @hf x y h1
    h2

set_option trace.Elab.definition.body true in
set_option pp.all true in
theorem inj_comp_1 {α β γ : Type} {f : α → β} {g : β → γ}
    (hg : Function.Injective g) (hf : Function.Injective f) :
    Function.Injective (g ∘ f) :=
  fun x y h => @hf x y (@hg (f x) (f y) h)

theorem inj_comp_2 {α β γ : Type} {f : α → β} {g : β → γ}
    (hg : Function.Injective g) (hf : Function.Injective f) :
    Function.Injective (g ∘ f) := by exact inj_comp hg hf


/-! ## 2. The term the kernel gets from the elaborator -/

/- Note that the theorem statement is also elaborated -/

set_option trace.Elab.definition.body true in
set_option pp.all true in
#print inj_comp

set_option pp.all true in
#print inj_comp

/-! ## 3. Replaying selected kernel checks
Each helper calls the kernel's own code. We choose the checks and their order to
follow the slides; this is not a recording of the original kernel execution. -/

/- Input: a term. Output: check it's type-/
def kCheck (e : Expr) : MetaM Expr := do
  ofExceptKernelException (Kernel.check (← getEnv) (← getLCtx) e)

/- Input: a term. Output: simplified version-/
def kWhnf (e : Expr) : MetaM Expr := do
  ofExceptKernelException (Kernel.whnf (← getEnv) (← getLCtx) e)

/-InputL two terms. Output: T/F if they are equal or not -/
def kDefEq (a b : Expr) : MetaM Bool := do
  ofExceptKernelException (Kernel.isDefEq (← getEnv) (← getLCtx) a b)

/- Put your cursor next to do on the line below to see the output in the InfoView -/
run_meta do
  let ci ← getConstInfo ``inj_comp
  let proof := ci.value! (allowOpaque := true)
  -- Show the point arguments of applications, while keeping types easy to read.
  let showApp (e : Expr) : MetaM Format :=
    withOptions (fun opts => opts.setBool `pp.explicit true) (ppExpr e)
  -- Enter the binders `α β γ f g hg hf x y h0` of the stored proof.
  lambdaTelescope proof fun xs body => do
    let (f, g, hg, hf, x, y, h0) :=
      (xs[3]!, xs[4]!, xs[5]!, xs[6]!, xs[7]!, xs[8]!, xs[9]!)
    let tg ← kCheck hg
    let tf ← kCheck hf
    let target ← instantiateForall ci.type (xs.extract 0 7)
    logInfo m!"0. Hypotheses and goal\n\
      f : {← kCheck f}\ng : {← kCheck g}\n\
      hg : {tg}\nhf : {tf}\n\
      T := {target}\nT : {← kCheck target}\n\
      After unfolding injectivity: {← kWhnf target}"

    let th0 ← kCheck h0
    let (_, lhs, rhs) := th0.eq?.get!
    logInfo m!"1. Inputs of the proof body\n\
      x : {← kCheck x}\ny : {← kCheck y}\nh0 : {th0}\n\
      Unfolding composition on each side:\n\
      {lhs} reduces to {← kWhnf lhs}\n\
      {rhs} reduces to {← kWhnf rhs}"

    -- Construct the wrong application directly as an Expr, so the kernel itself
    -- receives it. Catch the expected error so the rest of the demo still runs.
    let hfxy := mkApp2 hf x y
    let thfxy ← kCheck hfxy
    let bad := mkApp hfxy h0
    logInfo m!"2. A tempting wrong step\n\
      {← showApp hfxy} : {thfxy}\nh0 : {th0}"
    try
      let badType ← kCheck bad
      logInfo m!"The kernel accepts {← showApp bad} : {badType}"
    catch ex =>
      logInfo m!"The kernel rejects {← showApp bad}:\n{ex.toMessageData}"

    -- Read h1's actual declaration from the stored proof, then check its value.
    let h1Value := body.letValue!
    let fx := mkApp f x
    let fy := mkApp f y
    let hgfxfy := mkApp2 hg fx fy
    let thgfxfy ← kCheck hgfxfy
    let needed := (← kWhnf thgfxfy).bindingDomain!
    let h0Matches ← kDefEq th0 needed
    let inferredH1 ← kCheck h1Value
    logInfo m!"3. Checking h1 using injectivity of g\n\
      hg : {tg}\nAfter unfolding: {← kWhnf tg}\n\
      {fx} : {← kCheck fx}\n{fy} : {← kCheck fy}\n\
      {mkApp g fx} : {← kCheck (mkApp g fx)}\n\
      {mkApp g fy} : {← kCheck (mkApp g fy)}\n\
      {← showApp hgfxfy} : {thgfxfy}\n\
      Required input type: {needed}\nType of h0: {th0}\n\
      Definitionally equal: {h0Matches}\n\
      h1 := {← showApp h1Value}\nh1 : {inferredH1}"

    -- Record the checked local definition h1 so h2 can refer to it by name.
    withLetDecl body.letName! body.letType! h1Value fun h1 => do
      let rest := body.letBody!.instantiate1 h1
      let h2Value := rest.letValue!
      let inferredH2 ← kCheck h2Value
      logInfo m!"4. Checking h2 using injectivity of f\n\
        hf : {tf}\nAfter unfolding: {← kWhnf tf}\n\
        h1 : {← kCheck h1}\n\
        {← showApp (mkApp hf x)} : {← kCheck (mkApp hf x)}\n\
        {← showApp hfxy} : {thfxy}\n\
        h2 := {← showApp h2Value}\nh2 : {inferredH2}"
      withLetDecl rest.letName! rest.letType! h2Value fun h2 => do
        let result := rest.letBody!.instantiate1 h2
        logInfo m!"5. The body returns {result} : {← kCheck result}"

    -- Finally check the whole stored proof, including its let declarations, and
    -- compare the inferred type with the theorem's declared type.
    let inferred ← kCheck proof
    let typesMatch ← kDefEq inferred ci.type
    logInfo m!"6. Checking the complete proof\n\
      Inferred type: {inferred}\nDeclared type: {ci.type}\n\
      Definitionally equal: {typesMatch}"
