import { useMemo, useState } from 'react';
import { TextInput, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Chip, Segmented } from '@/components/ui/controls';
import { Sheet } from '@/components/ui/sheet';
import { FieldLabel, Mono, Txt, TxtMed } from '@/components/ui/text';
import { C, Font } from '@/theme/tokens';
import { formatSlot } from '@/domain/notifications';

/** Segmented is keyed by string, so the minutes round-trip through one. */
const DURATIONS = [
  { value: '20', label: '20 min' },
  { value: '30', label: '30 min' },
  { value: '45', label: '45 min' },
] as const;

const HOURS = [9, 11, 14, 16];

/** Next five weekdays, starting tomorrow. */
function upcomingDays(): Date[] {
  const out: Date[] = [];
  const cursor = new Date();
  cursor.setHours(0, 0, 0, 0);
  while (out.length < 5) {
    cursor.setDate(cursor.getDate() + 1);
    const day = cursor.getDay();
    if (day !== 0 && day !== 6) out.push(new Date(cursor));
  }
  return out;
}

/**
 * Investor proposes a slot. Sending writes a call request the founder answers
 * from their Investors tab; both sides get a notification.
 */
export function ScheduleCallSheet({
  visible,
  onClose,
  companyName,
  onSubmit,
}: {
  visible: boolean;
  onClose: () => void;
  companyName: string;
  onSubmit: (input: { proposedAt: string; durationMinutes: number; note: string }) => Promise<void>;
}) {
  const days = useMemo(upcomingDays, []);
  const [dayIndex, setDayIndex] = useState(0);
  const [hour, setHour] = useState(HOURS[1]);
  const [duration, setDuration] = useState<string>('30');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const proposedAt = useMemo(() => {
    const d = new Date(days[dayIndex]);
    d.setHours(hour, 0, 0, 0);
    return d.toISOString();
  }, [days, dayIndex, hour]);

  async function send() {
    setBusy(true);
    try {
      await onSubmit({ proposedAt, durationMinutes: Number(duration), note: note.trim() });
      setNote('');
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet visible={visible} onClose={onClose} title={`Schedule with ${companyName}`}>
      <View className="gap-[22px]">
        <View className="gap-[10px]">
          <FieldLabel>Day</FieldLabel>
          <View className="flex-row flex-wrap gap-[7px]">
            {days.map((d, i) => (
              <Chip
                key={d.toISOString()}
                label={d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}
                selected={i === dayIndex}
                onPress={() => setDayIndex(i)}
              />
            ))}
          </View>
        </View>

        <View className="gap-[10px]">
          <FieldLabel>Time</FieldLabel>
          <View className="flex-row flex-wrap gap-[7px]">
            {HOURS.map((h) => (
              <Chip
                key={h}
                label={`${String(h).padStart(2, '0')}:00`}
                selected={h === hour}
                onPress={() => setHour(h)}
              />
            ))}
          </View>
          <Txt className="text-[11px] text-ink-faint">Times are shown in your own timezone.</Txt>
        </View>

        <View className="gap-[10px]">
          <FieldLabel>Length</FieldLabel>
          <Segmented options={DURATIONS} value={duration} onChange={setDuration} grow size="md" />
        </View>

        <View className="gap-[10px]">
          <FieldLabel>Note to the founder</FieldLabel>
          <View className="rounded-[11px] border border-line-strong bg-surface-1 px-[14px] py-2" style={{ minHeight: 84 }}>
            <TextInput
              className="flex-1 text-[13.5px] text-ink"
              placeholder="What you want to cover on the call…"
              placeholderTextColor={C.inkFaint}
              value={note}
              onChangeText={setNote}
              multiline
              style={{ fontFamily: Font.regular, textAlignVertical: 'top', minHeight: 68 }}
            />
          </View>
        </View>

        <View className="rounded-[9px] border border-line bg-ground px-3 py-[10px]">
          <Txt className="text-[10px] text-ink-faint" style={{ letterSpacing: 0.5 }}>
            YOU ARE PROPOSING
          </Txt>
          <Mono className="mt-[3px] text-[13px]">
            {formatSlot(proposedAt)} · {duration} min
          </Mono>
        </View>

        <View className="gap-[9px]">
          <Button label="Send request" loading={busy} onPress={send} />
          <TxtMed className="text-center text-[11px] text-ink-faint">
            The founder gets a notification and can accept or decline.
          </TxtMed>
        </View>
      </View>
    </Sheet>
  );
}
