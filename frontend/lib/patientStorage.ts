import type { Patient } from "@/lib/api";

const KEY = "hospital-voice-patient";

export function loadPatient(): Patient | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const patient = JSON.parse(raw) as Patient;
    return typeof patient?.phone === "string" ? patient : null;
  } catch {
    return null;
  }
}

export function savePatient(patient: Patient): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(patient));
  } catch {
    /* storage unavailable: the login simply won't survive a refresh */
  }
}

export function clearPatient(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}