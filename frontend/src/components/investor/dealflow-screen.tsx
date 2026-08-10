import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/controls';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { CompanyCard } from './company-card';
import { FilterSheet } from './filter-sheet';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { DiscoveredStartup } from '@/domain/discovery';
import { route } from '@/lib/routes';
import { storage } from '@/lib/storage';
import { useInvestor } from '@/store/investor';
import { useNotifications } from '@/store/notifications';
import { useSession } from '@/store/session';
import { useThemeColors } from '@/theme/use-theme-colors';

const ORIENT_KEY = 'fundready.investor.dealflow.orient';

const PAGE = 20;

/**
 * Shared by the Dealflow and Watchlist tabs.
 *
 * Watchlist is local-only (device storage) until a sync endpoint exists —
 * it filters the discovery page client-side against starred startup ids.
 */
export function DealflowScreen({ mode }: { mode: 'deal' | 'watch' }) {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [rows, setRows] = useState<DiscoveredStartup[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showOrient, setShowOrient] = useState(false);
  const session = useSession((s) => s.session);

  const sector = useInvestor((s) => s.sector);
  const stage = useInvestor((s) => s.stage);
  const country = useInvestor((s) => s.country);
  const watchlist = useInvestor((s) => s.watchlist);
  const clearFilters = useInvestor((s) => s.clearFilters);
  const toggleWatch = useInvestor((s) => s.toggleWatch);
  const loadWatchlist = useInvestor((s) => s.loadWatchlist);
  const loadInterests = useInvestor((s) => s.loadInterests);
  const filterCount = useInvestor((s) => s.activeFilterCount());
  const unread = useNotifications((s) => s.unreadCount());

  const fetchPage = useCallback(
    async (nextOffset: number, replace: boolean) => {
      try {
        const page = await api.discoverStartups({
          sector: sector ?? undefined,
          stage: stage ?? undefined,
          country: country ?? undefined,
          limit: PAGE,
          offset: nextOffset,
        });
        let items = page.items;
        if (mode === 'watch') {
          const watched = new Set(watchlist);
          items = items.filter((s) => watched.has(s.startupId));
        }
        setRows((prev) => (replace ? items : [...prev, ...items]));
        setTotal(mode === 'watch' ? items.length : page.total);
        setOffset(nextOffset);
        setError(null);
      } catch (e: unknown) {
        if (replace) {
          setRows([]);
          setTotal(0);
        }
        setError(e);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [sector, stage, country, mode, watchlist],
  );

  useEffect(() => {
    void loadWatchlist();
    void loadInterests();
  }, [loadWatchlist, loadInterests]);

  useEffect(() => {
    if (mode !== 'deal') return;
    void storage.get(ORIENT_KEY).then((v) => {
      if (!v) setShowOrient(true);
    });
  }, [mode]);

  useEffect(() => {
    setLoading(true);
    setOffset(0);
    void fetchPage(0, true);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (mode === 'watch') return;
    if (loading || error) return;
    if (rows.length >= total) return;
    void fetchPage(offset + PAGE, false);
  }, [mode, loading, error, rows.length, total, offset, fetchPage]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void fetchPage(0, true);
  }, [fetchPage]);

  const title = mode === 'watch' ? 'Watchlist' : 'Dealflow';

  return (
    <View className="flex-1 bg-ground" style={{ paddingTop: insets.top + 4 }}>
      <View className="px-[18px] pb-3">
        <View className="h-[34px] flex-row items-center justify-between">
          <View className="flex-row items-center gap-2">
            <Mark size={16} />
            <TxtSemi className="text-[15px]" style={{ letterSpacing: -0.3 }}>
              {title}
            </TxtSemi>
          </View>
          <View className="flex-row items-center gap-[10px]">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={unread ? `Alerts, ${unread} unread` : 'Alerts'}
              onPress={() => router.push(route('/investor/alerts'))}
              className="h-[30px] w-[30px] items-center justify-center rounded-[8px] border border-line">
              <Txt className="text-[12px] text-ink-muted">◔</Txt>
              {unread > 0 ? (
                <View
                  className="absolute -right-[3px] -top-[3px] h-[13px] min-w-[13px] items-center justify-center rounded-full px-[3px]"
                  style={{ backgroundColor: colors.blue }}>
                  <Mono className="text-[8px] text-white">{unread > 9 ? '9+' : unread}</Mono>
                </View>
              ) : null}
            </Pressable>
            <View className="h-[28px] w-[28px] items-center justify-center rounded-full bg-line">
              <TxtSemi className="text-[10px] text-ink-muted">
                {(session?.displayName ?? 'I').slice(0, 2).toUpperCase()}
              </TxtSemi>
            </View>
          </View>
        </View>

        {mode === 'watch' ? (
          <Txt className="mt-[10px] text-[12px] text-ink-dim" style={{ lineHeight: 18 }}>
            Stars are saved on this device only until watchlists sync across devices. Open a company to
            express interest.
          </Txt>
        ) : (
          <View className="mt-[10px] gap-2">
            {showOrient ? (
              <View className="rounded-[11px] border border-line bg-surface-1 p-3">
                <TxtSemi className="text-[13px]">How dealflow works</TxtSemi>
                <Txt className="mt-1 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
                  Browse summary scores, star companies to watch, then express interest. FundReady AI
                  brokers every introduction — full diligence is not on this screen.
                </Txt>
                <View className="mt-2 self-start">
                  <Button
                    label="Got it"
                    height={34}
                    variant="secondary"
                    onPress={() => {
                      setShowOrient(false);
                      void storage.set(ORIENT_KEY, '1');
                    }}
                  />
                </View>
              </View>
            ) : null}
            <Txt className="text-[11.5px] text-ink-faint" style={{ lineHeight: 16 }}>
              Summary scores only — full diligence via FundReady AI.
            </Txt>
            <View className="flex-row items-center gap-[7px]">
              <Chip
                label="Filters"
                leading="⇅"
                onPress={() => setSheetOpen(true)}
                badge={filterCount || undefined}
              />
            </View>
          </View>
        )}
      </View>

      {loading && !rows.length ? (
        <View className="flex-1 items-center justify-center py-16">
          <ActivityIndicator color={colors.inkMuted} />
        </View>
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(c) => c.startupId}
          contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: 12, gap: 9 }}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.4}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.inkMuted} />
          }
          renderItem={({ item }) => (
            <CompanyCard
              startup={item}
              watched={watchlist.includes(item.startupId)}
              onPress={() => router.push(route(`/investor/company/${item.startupId}`))}
              onToggleWatch={() => toggleWatch(item.startupId)}
            />
          )}
          ListFooterComponent={
            rows.length && mode === 'deal' ? (
              <Txt className="py-2 text-center text-[11.5px] text-ink-faint">
                {`1–${rows.length} of ${total}`}
              </Txt>
            ) : null
          }
          ListEmptyComponent={
            error ? (
              <View className="px-1 py-6">
                <Unavailable
                  title={mode === 'watch' ? 'Watchlist could not load' : 'Dealflow could not load'}
                  error={error}
                  onRetry={() => {
                    setLoading(true);
                    void fetchPage(0, true);
                  }}
                />
              </View>
            ) : (
              <View className="items-center justify-center gap-[11px] px-6 py-[70px]">
                <View
                  className="h-[42px] w-[42px] items-center justify-center rounded-[11px]"
                  style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: colors.lineDash }}>
                  <Txt className="text-[16px] text-ink-ghost">⌕</Txt>
                </View>
                <TxtSemi className="text-center text-[14px]">
                  {mode === 'watch' ? 'Your watchlist is empty' : 'No startups match these filters'}
                </TxtSemi>
                <Txt className="text-center text-[12.5px] text-ink-dim" style={{ lineHeight: 19 }}>
                  {mode === 'watch'
                    ? 'Star a startup from dealflow to track it here, then open it to express interest.'
                    : 'Widen or reset filters, or check back once founders have published.'}
                </Txt>
                {mode === 'deal' ? (
                  <View className="mt-1 w-[160px]">
                    <Button label="Reset filters" height={36} onPress={clearFilters} />
                  </View>
                ) : (
                  <View className="mt-1 w-[180px]">
                    <Button
                      label="Browse dealflow"
                      height={36}
                      onPress={() => router.push(route('/investor'))}
                    />
                  </View>
                )}
              </View>
            )
          }
        />
      )}

      <FilterSheet visible={sheetOpen} onClose={() => setSheetOpen(false)} resultCount={total} />
    </View>
  );
}
