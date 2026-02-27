<template>
  <div class="card">
    <div class="flex items-center justify-between mb-3">
      <div>
        <p class="text-sm font-medium text-sekai-text">{{ title }}</p>
        <p v-if="subtitle" class="text-xs text-sekai-subtle mt-0.5">{{ subtitle }}</p>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="running" class="w-3 h-3 border-2 border-sekai-warning border-t-transparent rounded-full animate-spin" />
        <StatusBadge :status="badgeStatus" />
      </div>
    </div>

    <!-- Slot for extra content (e.g. preview image) -->
    <slot />

    <!-- Run button -->
    <button
      v-if="canRun && !running"
      class="btn-primary w-full mt-3 text-sm"
      @click="$emit('run')"
    >
      Run
    </button>
    <div v-else-if="running" class="mt-3 text-xs text-sekai-warning text-center animate-pulse-slow">
      Running…
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  title:    String,
  subtitle: String,
  status:   String,   // 'locked' | 'ready' | 'running' | 'done' | 'error'
  canRun:   Boolean,
  running:  Boolean,
})
defineEmits(['run'])

const STATUS_TO_BADGE = {
  locked:  'pending_approval',
  ready:   'approved',
  running: 'running',
  done:    'uploaded',
  error:   'error',
}

const badgeStatus = computed(() => {
  if (props.running) return 'running'
  return STATUS_TO_BADGE[props.status] ?? 'pending_approval'
})
</script>
