import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { Eyebrow, FieldLabel, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { RegistryEntry } from '@/domain/readiness';
import { putToSignedUrl } from '@/lib/upload';
import { useFounder } from '@/store/founder';

const MAX_DOC_BYTES = 10 * 1024 * 1024;

/**
 * Store legal registration details + certificate on the startup profile.
 *
 * There is no server "verified company" switch yet — this uploads a
 * `registration_certificate` document for FundReady AI and saves profile fields.
 * Publishing still depends on the readiness gate.
 */
export default function VerifyCompany() {
  const insets = useSafeAreaInsets();
  const profile = useFounder((s) => s.profile);
  const setField = useFounder((s) => s.setField);
  const save = useFounder((s) => s.save);

  const [registries, setRegistries] = useState<RegistryEntry[]>([]);
  const [country, setCountry] = useState('');
  const [legalName, setLegalName] = useState(profile.legalName || '');
  const [registrationNumber, setRegistrationNumber] = useState(profile.registrationNumber || '');
  const [registrar, setRegistrar] = useState(profile.registrar || '');
  const [incorporationYear, setIncorporationYear] = useState(profile.incorporationYear);
  const [regulatoryLicences, setRegulatoryLicences] = useState(profile.regulatoryLicences);
  const [documentName, setDocumentName] = useState('');
  const [pickedUri, setPickedUri] = useState<string | null>(null);
  const [pickedMime, setPickedMime] = useState('application/pdf');
  const [docError, setDocError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    void api
      .listRegistries()
      .then((rows) => {
        setRegistries(rows);
        setCountry((current) => {
          if (current || !rows[0]) return current;
          setRegistrar(rows[0].shortName || rows[0].registrar);
          return rows[0].countryName;
        });
      })
      .catch(() => {
        // Fall back to free-text country if registries fail.
      });
  }, []);

  const countryOptions = registries.length
    ? registries.map((r) => r.countryName)
    : ['Nigeria', 'Ghana', 'Kenya', 'South Africa', 'United Kingdom', 'United States', 'Other'];

  const complete = country && legalName.trim() && registrationNumber.trim() && (documentName || pickedUri);

  function pickCountry(value: string) {
    setCountry(value);
    const match = registries.find((r) => r.countryName === value);
    if (match) setRegistrar(match.shortName || match.registrar);
  }

  async function pickDocument() {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png'],
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const file = result.assets[0];
    if ((file.size ?? 0) > MAX_DOC_BYTES) {
      setDocError('File exceeds 10 MB. Compress the scan and try again.');
      return;
    }
    setDocError(null);
    setDocumentName(file.name);
    setPickedUri(file.uri);
    setPickedMime(file.mimeType || 'application/pdf');
  }

  async function submit() {
    if (!complete) {
      setTouched(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setField('legalName', legalName.trim());
      setField('registrationNumber', registrationNumber.trim());
      setField('registrar', registrar.trim());
      setField('incorporationYear', incorporationYear.trim());
      setField('regulatoryLicences', regulatoryLicences.trim());
      // Country on the profile is free text today; registries give the label.
      if (!profile.location.trim()) setField('location', country);
      await save();

      if (pickedUri && documentName) {
        const ticket = await api.beginDocumentUpload({
          kind: 'registration_certificate',
          filename: documentName,
          contentType: pickedMime,
        });
        const blob = await (await fetch(pickedUri)).blob();
        await putToSignedUrl(ticket.uploadUrl, blob, pickedMime, ticket.maxBytes);
        await api.completeDocumentUpload(ticket.documentId);
      }

      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View className="border-b border-line-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
            <Txt className="text-[19px] text-ink">←</Txt>
          </Pressable>
          <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
            REGISTRATION
          </Mono>
          <View className="w-5" />
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingTop: 20 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <Eyebrow>REGISTRATION</Eyebrow>
        <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
          Store your company registration
        </TxtSemi>
        <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
          Details and the certificate are saved for audits and FundReady AI review. This does not by itself
          put you in dealflow — clear readiness tasks, then publish from Home.
        </Txt>

        {done ? (
          <View
            className="mb-5 rounded-[12px] p-[14px]"
            style={{ borderWidth: 1, borderColor: 'rgba(12,206,107,0.30)', backgroundColor: 'rgba(12,206,107,0.07)' }}>
            <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.grn }}>
              SAVED
            </Mono>
            <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              Registration details and certificate are on your profile. Return to Home to publish when the readiness
              gate is clear.
            </Txt>
            <View className="mt-3">
              <Button label="Back to Home" height={40} onPress={() => router.back()} />
            </View>
          </View>
        ) : null}

        <View className="gap-4">
          <Select
            label="Country of registration"
            placeholder="Select a country…"
            value={country}
            options={countryOptions}
            onChange={pickCountry}
          />
          <Field
            label="Registered legal name"
            placeholder="Northwind Labs Limited"
            value={legalName}
            onChangeText={setLegalName}
          />
          <Field
            label="Registration number"
            placeholder="RC 1234567"
            value={registrationNumber}
            onChangeText={setRegistrationNumber}
            autoCapitalize="characters"
            mono
          />
          <Field
            label="Registered with"
            placeholder="CAC"
            value={registrar}
            onChangeText={setRegistrar}
            hint="The government body you filed with."
          />
          <Field
            label="Year incorporated"
            placeholder="2023"
            value={incorporationYear}
            onChangeText={setIncorporationYear}
            keyboardType="number-pad"
            mono
          />
          <Field
            label="Licences your model needs"
            placeholder="None needed"
            value={regulatoryLicences}
            onChangeText={setRegulatoryLicences}
            multiline
          />

          <View className="gap-[9px]">
            <FieldLabel>Certificate of incorporation</FieldLabel>
            {documentName ? (
              <View className="flex-row items-center gap-[11px] rounded-[11px] border border-line-strong bg-surface-1 p-[14px]">
                <View className="h-[34px] w-[34px] items-center justify-center rounded-[7px] border border-line-strong bg-surface-3">
                  <Mono className="text-[9px] text-ink-muted">
                    {documentName.split('.').pop()?.slice(0, 4).toUpperCase() ?? 'DOC'}
                  </Mono>
                </View>
                <View className="min-w-0 flex-1">
                  <Txt className="text-[13px]" numberOfLines={1}>
                    {documentName}
                  </Txt>
                  <Txt className="text-[11px] text-ink-faint">ready to upload</Txt>
                </View>
                <Pressable accessibilityRole="button" onPress={pickDocument} hitSlop={8}>
                  <Txt className="text-[11.5px] text-ink-muted">Replace</Txt>
                </Pressable>
              </View>
            ) : (
              <Pressable
                accessibilityRole="button"
                onPress={pickDocument}
                className="w-full items-center gap-[6px] rounded-[11px] bg-surface-1 px-4 py-[26px]"
                style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.lineDash }}>
                <Txt className="text-[19px] text-ink">↑</Txt>
                <TxtMed className="text-[13.5px] text-ink">Upload certificate</TxtMed>
                <Txt className="text-[11px] text-ink-faint">PDF, JPG or PNG · up to 10 MB</Txt>
              </Pressable>
            )}
            {docError ? <ErrorNote text={docError} /> : null}
          </View>

          {touched && !complete ? <ErrorNote text="Fill every field and attach your certificate." /> : null}
        </View>

        {error ? <Unavailable title="Could not save registration" error={error} className="mt-5" /> : null}
      </ScrollView>

      <View className="border-t border-line-soft bg-ground px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <Button label="Save registration" height={48} loading={busy} disabled={done} onPress={submit} />
      </View>
    </KeyboardAvoidingView>
  );
}

function ErrorNote({ text }: { text: string }) {
  return (
    <View
      className="rounded-[9px] px-[13px] py-[11px]"
      style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
      <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
        {text}
      </Txt>
    </View>
  );
}
