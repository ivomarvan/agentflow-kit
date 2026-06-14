<template>
  <div class="hb-panel">
    <div class="hb-header">
      <span class="hb-title">🏨 Hotel Guest Book</span>
      <span v-if="lastAction" class="hb-last-action">{{ lastAction }}</span>
    </div>

    <div class="hb-scroll">
      <table class="hb-table">
        <thead>
          <tr>
            <th class="hb-row-head hb-corner">Room</th>
            <th
              v-for="day in dateColumns"
              :key="day.iso"
              class="hb-day-head"
            >
              {{ day.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="room in rooms" :key="room.room_id" :style="{ background: roomRowBg(room.room_id) }">
            <th class="hb-row-head" :style="{ background: roomRowBg(room.room_id) }">
              <div class="hb-room-name">🛏 {{ room.name }}</div>
              <div class="hb-room-meta">×{{ room.capacity }} beds · €{{ room.price_per_night }}/night</div>
            </th>
            <td
              v-for="day in dateColumns"
              :key="`${room.room_id}-${day.iso}`"
              :class="['hb-cell', {
                occupied: cellGuest(room, day.iso),
                flash: isFlashing(room.room_id, day.iso),
              }]"
              :style="!cellGuest(room, day.iso) ? { background: roomCellBg(room.room_id) } : {}"
            >
              {{ cellGuest(room, day.iso) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="lastAction" class="hb-status">{{ lastAction }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Reservation {
  reservation_id: string
  guest_name: string
  check_in: string
  check_out: string
  total_price: number
}

interface RoomState {
  room_id: string
  name: string
  capacity: number
  price_per_night: number
  reservations: Reservation[]
}

interface Props {
  rooms: RoomState[]
  lastAction?: string
}

const props = withDefaults(defineProps<Props>(), {
  lastAction: '',
})

interface DayColumn {
  iso: string
  label: string
  date: Date
}

function addDays(d: Date, n: number): Date {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

function toIso(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function formatDayLabel(d: Date): string {
  return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' })
}

function computeDateRange(roomList: RoomState[]): Date[] {
  const allReservations = roomList.flatMap((r) => r.reservations)
  if (allReservations.length === 0) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return Array.from({ length: 8 }, (_, i) => addDays(today, i))
  }

  let minIn = new Date(allReservations[0].check_in)
  let maxOut = new Date(allReservations[0].check_out)
  for (const res of allReservations) {
    const cin = new Date(res.check_in)
    const cout = new Date(res.check_out)
    if (cin < minIn) minIn = cin
    if (cout > maxOut) maxOut = cout
  }

  const start = addDays(minIn, -1)
  const end = maxOut
  const days: Date[] = []
  for (let d = new Date(start); d <= end; d = addDays(d, 1)) {
    days.push(new Date(d))
  }
  return days
}

const dateColumns = computed((): DayColumn[] =>
  computeDateRange(props.rooms).map((d) => ({
    iso: toIso(d),
    label: formatDayLabel(d),
    date: d,
  })),
)

function cellGuest(room: RoomState, dayIso: string): string {
  const day = new Date(dayIso)
  for (const res of room.reservations) {
    const cin = new Date(res.check_in)
    const cout = new Date(res.check_out)
    if (day >= cin && day < cout) {
      return res.guest_name.substring(0, 5)
    }
  }
  return ''
}

const prevRooms = ref<RoomState[] | null>(null)
const flashCells = ref<Set<string>>(new Set())

function diffFlashCells(before: RoomState[], after: RoomState[]): Set<string> {
  const changed = new Set<string>()
  const days = computeDateRange(after).map(toIso)
  for (const room of after) {
    const prevRoom = before.find((r) => r.room_id === room.room_id)
    for (const dayIso of days) {
      const was = prevRoom ? cellGuest(prevRoom, dayIso) : ''
      const now = cellGuest(room, dayIso)
      if (was !== now) changed.add(`${room.room_id}/${dayIso}`)
    }
  }
  return changed
}

function triggerFlash(before: RoomState[], after: RoomState[]) {
  flashCells.value = diffFlashCells(before, after)
  setTimeout(() => { flashCells.value = new Set() }, 600)
}

watch(
  () => props.rooms,
  (next) => {
    if (prevRooms.value) triggerFlash(prevRooms.value, next)
    prevRooms.value = structuredClone(next)
  },
  { deep: true },
)

function isFlashing(roomId: string, dayIso: string): boolean {
  return flashCells.value.has(`${roomId}/${dayIso}`)
}

// Subtle row background tinted by room colour.
const ROOM_ROW_BG: Record<string, string> = {
  red:   'rgba(220, 60,  60,  0.06)',
  blue:  'rgba(60,  120, 220, 0.07)',
  green: 'rgba(40,  160, 80,  0.07)',
  white: 'rgba(160, 160, 160, 0.06)',
}

// Slightly more visible for empty data cells (header cell uses the same value).
const ROOM_CELL_BG: Record<string, string> = {
  red:   'rgba(220, 60,  60,  0.04)',
  blue:  'rgba(60,  120, 220, 0.05)',
  green: 'rgba(40,  160, 80,  0.05)',
  white: 'rgba(160, 160, 160, 0.04)',
}

function roomRowBg(roomId: string): string {
  return ROOM_ROW_BG[roomId] ?? 'transparent'
}

function roomCellBg(roomId: string): string {
  return ROOM_CELL_BG[roomId] ?? 'transparent'
}
</script>

<style scoped>
.hb-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 480px;
  overflow: hidden;
}

.hb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.25rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color);
  background: var(--p-surface-section);
  flex-shrink: 0;
}

.hb-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-text-muted-color);
}

.hb-last-action {
  font-size: 0.65rem;
  color: var(--p-text-muted-color);
  max-width: 50%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hb-scroll {
  flex: 1;
  overflow-x: auto;
  overflow-y: auto;
  padding: 0.4rem;
}

.hb-table {
  border-collapse: collapse;
  font-size: 0.7rem;
}

.hb-corner {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--p-surface-section);
}

.hb-row-head {
  position: sticky;
  left: 0;
  z-index: 1;
  width: 160px;
  min-width: 160px;
  text-align: left;
  vertical-align: middle;
  padding: 0.35rem 0.5rem;
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
}

.hb-room-name {
  font-weight: 600;
  color: var(--p-text-color);
}

.hb-room-meta {
  font-size: 0.62rem;
  color: var(--p-text-muted-color);
  margin-top: 0.15rem;
}

.hb-day-head {
  min-width: 52px;
  width: 52px;
  padding: 0.3rem 0.2rem;
  text-align: center;
  font-weight: 600;
  background: var(--p-surface-200);
  border: 1px solid var(--p-content-border-color);
  color: var(--p-text-muted-color);
}

.hb-cell {
  width: 52px;
  min-width: 52px;
  height: 32px;
  text-align: center;
  vertical-align: middle;
  border: 1px solid var(--p-content-border-color);
  background: var(--p-surface-ground);
  color: var(--p-text-muted-color);
  font-size: 0.62rem;
  font-weight: 600;
}

.hb-cell.occupied {
  background: var(--p-amber-100);
  color: var(--p-amber-700);
}

.hb-cell.flash {
  animation: cell-flash 0.6s ease-out;
}

@keyframes cell-flash {
  0% { background: var(--p-amber-300); }
  100% { background: var(--p-amber-100); }
}

.hb-status {
  flex-shrink: 0;
  padding: 0.3rem 0.6rem;
  font-size: 0.68rem;
  color: var(--p-text-muted-color);
  border-top: 1px solid var(--p-content-border-color);
  background: var(--p-surface-ground);
}
</style>
