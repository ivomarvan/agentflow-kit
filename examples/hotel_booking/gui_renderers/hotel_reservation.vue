<template>
  <div class="reservation-event">
    <span class="event-badge">🏨 Reservation</span>
    <table class="reservation-table">
      <tbody>
        <tr><td class="label">Guest</td><td>{{ event.guest_name }}</td></tr>
        <tr><td class="label">Room</td><td>{{ event.room }}</td></tr>
        <tr><td class="label">Check-in</td><td>{{ event.check_in }}</td></tr>
        <tr><td class="label">Check-out</td><td>{{ event.check_out }}</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
defineProps<{ event: Record<string, unknown> }>()
</script>

<style scoped>
.reservation-event {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 0.8rem;
}
.event-badge {
  font-weight: 600;
  color: #166534;
  font-size: 0.75rem;
}
.reservation-table { border-collapse: collapse; }
.reservation-table td { padding: 1px 6px; }
.reservation-table .label { font-weight: 600; color: #374151; }
</style>
