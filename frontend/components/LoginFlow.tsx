"use client";

import { FormEvent, useState } from "react";
import { Alert, BrandMark, Button, Spinner, TextField } from "@/components/ui";
import { ApiError, loginPatient, registerPatient, type Patient } from "@/lib/api";

type Mode = "new" | "existing";
type Step = "choose" | "form" | "otp";

type Props = { onSuccess: (patient: Patient) => void };

export default function LoginFlow({ onSuccess }: Props) {
  const [step, setStep] = useState<Step>("choose");
  const [mode, setMode] = useState<Mode>("existing");
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [switchTo, setSwitchTo] = useState<{ label: string; mode: Mode } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const stepNumber = step === "choose" ? 1 : step === "form" ? 2 : 3;

  function choose(next: Mode) {
    setMode(next);
    setError(null);
    setSwitchTo(null);
    setStep("form");
  }

  function validateForm(): string | null {
    if (!/^\d{10}$/.test(phone)) return "Enter a 10-digit phone number.";
    if (mode === "new") {
      if (name.trim().length < 1 || name.trim().length > 100) {
        return "Enter your name (up to 100 characters).";
      }
      const years = Number(age);
      if (age === "" || !Number.isInteger(years) || years < 0 || years > 120) {
        return "Enter an age between 0 and 120.";
      }
    }
    return null;
  }

  function submitForm(e: FormEvent) {
    e.preventDefault();
    const problem = validateForm();
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setOtp("");
    setStep("otp");
  }

  async function verifyOtp(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit code.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSwitchTo(null);
    try {
      const patient =
        mode === "new"
          ? await registerPatient({ name: name.trim(), age: Number(age), phone })
          : await loginPatient(phone);
      onSuccess(patient);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (mode === "existing" && err.status === 404) {
          setSwitchTo({ label: "Register as a new patient", mode: "new" });
        } else if (mode === "new" && err.status === 409) {
          setSwitchTo({ label: "Log in as an existing patient", mode: "existing" });
        }
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    if (!switchTo) return;
    setMode(switchTo.mode);
    setSwitchTo(null);
    setError(null);
    setOtp("");
    setStep("form"); // the phone number stays filled in
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-sky-50 to-white px-4 py-10">
      <div className="mb-6">
        <BrandMark />
      </div>

      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-teal-700">Step {stepNumber} of 3</p>

        {step === "choose" && (
          <div className="mt-2 flex flex-col gap-3">
            <h1 className="text-xl font-semibold text-slate-900">Welcome</h1>
            <p className="text-sm text-slate-600">Are you a new or an existing patient?</p>
            <Button onClick={() => choose("new")}>I&apos;m a new patient</Button>
            <Button variant="secondary" onClick={() => choose("existing")}>
              I&apos;m an existing patient
            </Button>
          </div>
        )}

        {step === "form" && (
          <form className="mt-2 flex flex-col gap-4" onSubmit={submitForm} noValidate>
            <h1 className="text-xl font-semibold text-slate-900">
              {mode === "new" ? "Create your patient record" : "Log in"}
            </h1>
            {mode === "new" && (
              <>
                <TextField
                  label="Full name"
                  autoComplete="name"
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <TextField
                  label="Age"
                  inputMode="numeric"
                  maxLength={3}
                  value={age}
                  onChange={(e) => setAge(e.target.value.replace(/\D/g, ""))}
                />
              </>
            )}
            <TextField
              label="Phone number"
              autoComplete="tel"
              inputMode="numeric"
              maxLength={10}
              placeholder="10 digits"
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
            />
            {error && <Alert>{error}</Alert>}
            <Button type="submit">Continue</Button>
            <Button variant="ghost" onClick={() => setStep("choose")}>
              Back
            </Button>
          </form>
        )}

        {step === "otp" && (
          <form className="mt-2 flex flex-col gap-4" onSubmit={verifyOtp} noValidate>
            <h1 className="text-xl font-semibold text-slate-900">Verify your number</h1>
            <p className="text-sm text-slate-600">
              We sent a 6-digit code to {phone}.{" "}
              <span className="text-slate-400">(Demo: any 6 digits work.)</span>
            </p>
            <TextField
              label="Verification code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              autoFocus
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
            />
            {error && <Alert>{error}</Alert>}
            {switchTo && (
              <Button variant="secondary" onClick={switchMode}>
                {switchTo.label}
              </Button>
            )}
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <>
                  <Spinner /> Checking…
                </>
              ) : (
                "Verify"
              )}
            </Button>
            <Button variant="ghost" disabled={submitting} onClick={() => setStep("form")}>
              Back
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}