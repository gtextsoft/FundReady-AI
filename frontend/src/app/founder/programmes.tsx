import { useCallback, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { Button } from '@/components/ui/button';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { CatalogueProduct, Enrolment } from '@/domain/types';
import { useFounder } from '@/store/founder';

const ACCENTS: Record<string, { accent: string; border: string; gradient: [string, string]; variant: 'amber' | 'green' | 'primary' }> = {
  'funding-readiness-challenge': {
    accent: C.amb,
    border: '#3d2f14',
    gradient: ['rgba(245,166,35,0.14)', 'rgba(245,166,35,0.02)'],
    variant: 'amber',
  },
  'wealth-creation-challenge': {
    accent: C.grn,
    border: '#14351f',
    gradient: ['rgba(12,206,107,0.14)', 'rgba(12,206,107,0.02)'],
    variant: 'green',
  },
};

const DEFAULT_ACCENT = {
  accent: C.blue,
  border: '#1a2a3d',
  gradient: ['rgba(59,130,246,0.14)', 'rgba(59,130,246,0.02)'] as [string, string],
  variant: 'primary' as const,
};

function programmeKey(slug: string): 'readiness' | 'wealth' | null {
  if (slug === 'funding-readiness-challenge') return 'readiness';
  if (slug === 'wealth-creation-challenge') return 'wealth';
  return null;
}

export default function Programmes() {
  const insets = useSafeAreaInsets();
  const assessment = useFounder((s) => s.assessment);
  const [products, setProducts] = useState<CatalogueProduct[]>([]);
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const recommended = assessment?.route ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [page, mine] = await Promise.all([api.listProducts({ limit: 50 }), api.listEnrolments()]);
      setProducts(page.items.filter((p) => p.active));
      setEnrolments(mine);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const enrolledIds = new Set(enrolments.map((e) => e.productId));

  async function enrol(product: CatalogueProduct) {
    setBusy(product.id);
    setError(null);
    try {
      const result = await api.enrolInProduct(product.id);
      if (result.status === 'checkout_required' && result.checkoutUrl) {
        await Linking.openURL(result.checkoutUrl);
      } else {
        setEnrolments((prev) =>
          result.enrolment ? [result.enrolment, ...prev.filter((e) => e.id !== result.enrolment!.id)] : prev,
        );
      }
      // Refresh after checkout return / free enrol.
      const mine = await api.listEnrolments();
      setEnrolments(mine);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <View className="flex-1 bg-ground">
      <View className="flex-row items-center justify-between px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          PROGRAMMES
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: insets.bottom + 24, gap: 12 }}
        showsVerticalScrollIndicator={false}>
        {error ? <Unavailable title="Could not load programmes" error={error} onRetry={load} /> : null}

        {loading ? (
          <View className="items-center py-16">
            <ActivityIndicator color={C.inkMuted} />
          </View>
        ) : products.length === 0 ? (
          <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
            <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              No programmes in the catalogue yet. Check back after FundReady AI publishes the next cohort.
            </Txt>
          </View>
        ) : (
          products.map((p) => {
            const style = ACCENTS[p.slug] ?? DEFAULT_ACCENT;
            const key = programmeKey(p.slug);
            const isRecommended = key != null && recommended === key;
            const done = enrolledIds.has(p.id);
            return (
              <View key={p.id} className="overflow-hidden rounded-[14px]" style={{ borderWidth: 1, borderColor: style.border }}>
                <LinearGradient colors={style.gradient} start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }} className="p-5">
                  <View className="flex-row items-center gap-2">
                    <View className="rounded-[4px] px-[7px] py-[3px]" style={{ borderWidth: 1, borderColor: `${style.accent}59` }}>
                      <Mono className="text-[9.5px]" style={{ letterSpacing: 1.2, color: style.accent }}>
                        {p.kind.toUpperCase()}
                      </Mono>
                    </View>
                    {isRecommended ? (
                      <View className="rounded-[4px] bg-ink px-[7px] py-[3px]">
                        <Mono className="text-[9.5px] text-ground" style={{ letterSpacing: 1 }}>
                          RECOMMENDED
                        </Mono>
                      </View>
                    ) : null}
                  </View>

                  <TxtSemi className="mb-[6px] mt-[13px] text-[21px]" style={{ letterSpacing: -0.6 }}>
                    {p.title}
                  </TxtSemi>
                  <Txt className="mb-4 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
                    {p.description}
                  </Txt>

                  {p.amountMinor != null && p.currency ? (
                    <Txt className="mb-3 text-[12px] text-ink-dim">
                      {p.currency} {(p.amountMinor / 100).toLocaleString()}
                    </Txt>
                  ) : null}

                  <Button
                    label={done ? 'Enrolled ✓' : p.amountMinor != null ? 'Enrol — pay to confirm' : 'Enrol'}
                    variant={style.variant}
                    loading={busy === p.id}
                    disabled={done || busy !== null}
                    onPress={() => enrol(p)}
                  />
                </LinearGradient>
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}
