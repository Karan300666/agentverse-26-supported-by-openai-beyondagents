"use client";

import LoginFlow from "@/components/LoginFlow";
import VoiceCall from "@/components/VoiceCall";
import { useAuth } from "@/hooks/useAuth";

export default function Home() {
  const { patient, ready, signIn, signOut } = useAuth();

  if (!ready) return null; // wait until the stored login has been read

  return patient ? <VoiceCall patient={patient} onLogout={signOut} /> : <LoginFlow onSuccess={signIn} />;
}