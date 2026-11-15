"use client";

import { useCallback, useEffect, useState } from "react";
import type { Patient } from "@/lib/api";
import { clearPatient, loadPatient, savePatient } from "@/lib/patientStorage";

export function useAuth() {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [ready, setReady] = useState(false); // false until sessionStorage has been read

  useEffect(() => {
    setPatient(loadPatient());
    setReady(true);
  }, []);

  const signIn = useCallback((next: Patient) => {
    savePatient(next);
    setPatient(next);
  }, []);

  const signOut = useCallback(() => {
    clearPatient();
    setPatient(null);
  }, []);

  return { patient, ready, signIn, signOut };
} 