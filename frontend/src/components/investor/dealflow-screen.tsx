import { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/controls';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { CompanyCard } from './company-card';
import { FilterSheet } from './filter-sheet';
import { C, Font } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api, type CompanySummary } from '@/api';
import type { SortKey } from '@/domain/types';
import { route } from '@/lib/routes';
import { useInvestor } from '@/store/investor';
import { useNotifications } from '@/store/notifications';
import { useSession } from '@/store/session';

const PAGE = 12;

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'score', label: 'Top score' },
  { value: 'new', label: 'Newest' },
  { value: 'rev', label: 'Revenue' },
];

/**
 * Shared by the Dealflow and Watchlist tabs — same data, same filters, the
 * watchlist just restricts the id set and changes the empty-state copy.
 */
export function DealflowScreen({ mode }: { mode: 'deal' | 'watch' }) {
  const insets = useSafeAreaInsets();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [rows, setRows] = useState<CompanySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(PAGE);
  const [error, setError] = useState<unknown>(null);
  const session = useSession((s) => s.session);

  const query = useInvestor((s) => s.query);
  const minScore = useInvestor((s) => s.minScore);
  const match = useInvestor((s) => s.match);
  const sectors = useInvestor((s) => s.sectors);
  const stages = useInvestor((s) => s.stages);
  const sort = useInvestor((s) => s.sort);
  const watchlist = useInvestor((s) => s.watchlist);
  const setQuery = useInvestor((s) => s.setQuery);
  const setSort = useInvestor((s) => s.setSort);
  const clearFilters = useInvestor((s) => s.clearFilters);
  const toggleWatch = useInvestor((s) => s.toggleWatch);
  const filterCount = useInvestor((s) => s.activeFilterCount());
  const unread = useNotifications((s) => s.unreadCount());

  const request = useMemo(
    () => ({
      query,
      minScore,
      match,
      sectors,
      stages,
      sort,
      ids: mode === 'watch' ? watchlist : undefined,
    }),
    [query, minScore, match, sectors, stages, sort, mode, watchlist],
  );

  useEffect(() => {
    let live = true;
    // `limit` grows as the list is scrolled — one page request covers it all.
    api
      .listCompanies(request, 1, limit)
      .then((page) => {
        if (!live) return;
        setRows(page.rows);
        setTotal(page.total);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!live) return;
        setRows([]);
        setTotal(0);
        setError(e);
      });
    return () => {
      live = false;
    };
  }, [request, limit]);

  // A changed filter should return the list to the top of its first page.
  useEffect(() => {
    setLimit(PAGE);
  }, [query, minScore, match, sectors, stages, sort, mode]);

  const loadMore = useCallback(() => {
    setLimit((n) => (n < total ? n + PAGE : n));
  }, [total]);

  const title = mode === 'watch' ? 'Watchlist' : 'Dealflow';

  return (
    <View className="flex-1 bg-ground" style={{ paddingTop: insets.top + 4 }}>
      {/* header */}
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
                  style={{ backgroundColor: C.blue }}>
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

        {/* search */}
        <View className="mt-[10px] h-[38px] flex-row items-center gap-[9px] rounded-[9px] border border-line bg-surface-1 px-3">
          <Txt className="text-[13px] text-ink-faint">⌕</Txt>
          <TextInput
            className="min-w-0 flex-1 text-[13.5px] text-ink"
            placeholder="Search company, sector, founder"
            placeholderTextColor={C.inkFaint}
            value={query}
            onChangeText={setQuery}
            autoCapitalize="none"
            style={{ fontFamily: Font.regular, padding: 0 }}
          />
        </View>

        {/* filter + sort rail */}
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ marginTop: 10, flexGrow: 0 }}
          contentContainerStyle={{ gap: 7, alignItems: 'center' }}
          data={SORTS}
          keyExtractor={(s) => s.value}
          ListHeaderComponent={
            <View className="flex-row items-center gap-[7px]">
              <Chip
                label="Filters"
                leading="⇅"
                onPress={() => setSheetOpen(true)}
                badge={filterCount || undefined}
              />
              <View className="h-[18px] w-[1px] bg-line" />
            </View>
          }
          renderItem={({ item }) => (
            <Chip label={item.label} selected={sort === item.value} onPress={() => setSort(item.value)} />
          )}
        />
      </View>

      {/* list */}
      <FlatList
        data={rows}
        keyExtractor={(c) => String(c.id)}
        contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: 12, gap: 9 }}
        showsVerticalScrollIndicator={false}
        onEndReached={loadMore}
        onEndReachedThreshold={0.4}
        renderItem={({ item }) => (
          <CompanyCard
            company={item}
            watched={watchlist.includes(item.id)}
            onPress={() => router.push(route(`/investor/company/${item.id}`))}
            onToggleWatch={() => toggleWatch(item.id)}
          />
        )}
        ListFooterComponent={
          rows.length ? (
            <Txt className="py-2 text-center text-[11.5px] text-ink-faint">
              {`1–${rows.length} of ${total}`}
            </Txt>
          ) : null
        }
        ListEmptyComponent={
          error ? (
            <View className="px-1 py-6">
              <Unavailable
                title={mode === 'watch' ? 'The watchlist is not live' : 'Dealflow is not live'}
                error={error}
              />
            </View>
          ) : (
            <View className="items-center justify-center gap-[11px] px-6 py-[70px]">
              <View
                className="h-[42px] w-[42px] items-center justify-center rounded-[11px]"
                style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.lineDash }}>
                <Txt className="text-[16px] text-ink-ghost">⌕</Txt>
              </View>
              <TxtSemi className="text-center text-[14px]">
                {mode === 'watch' ? 'Your watchlist is empty' : 'No companies match these filters'}
              </TxtSemi>
              <Txt className="text-center text-[12.5px] text-ink-dim" style={{ lineHeight: 19 }}>
                {mode === 'watch'
                  ? 'Star a company from the dealflow table and it will be tracked here with score-change alerts.'
                  : 'Widen the score range or clear a sector to see more of the companies currently listed.'}
              </Txt>
              <View className="mt-1 w-[160px]">
                <Button label="Reset filters" height={36} onPress={clearFilters} />
              </View>
            </View>
          )
        }
      />

      <FilterSheet visible={sheetOpen} onClose={() => setSheetOpen(false)} resultCount={total} />
    </View>
  );
}
