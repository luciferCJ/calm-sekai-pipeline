<template>
  <div class="card flex flex-col gap-3 animate-fade-in">

    <!-- Header: theme + status + edit toggle -->
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1 min-w-0">
        <p v-if="!editing" class="text-sm font-medium text-sekai-text truncate">{{ local.theme }}</p>
        <input v-else v-model="local.theme" class="input text-sm font-medium w-full" @blur="save('theme', local.theme)" />
        <p v-if="!editing" class="text-xs text-sekai-subtle mt-0.5">{{ local.emotion }}</p>
        <input v-else v-model="local.emotion" class="input text-xs mt-1 w-full" @blur="save('emotion', local.emotion)" />
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <button
          v-if="canEdit"
          class="text-xs text-sekai-subtle hover:text-sekai-accent transition-colors px-1"
          @click="editing = !editing"
        >
          {{ editing ? 'Done' : 'Edit' }}
        </button>
        <StatusBadge :status="concept.status" />
      </div>
    </div>

    <!-- Format pill (editable) -->
    <div class="flex gap-2">
      <template v-if="!editing">
        <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
          {{ local.format === 'shorts_10s' ? '10s Short' : '30s Short' }}
        </span>
      </template>
      <template v-else>
        <select v-model="local.format" class="input text-xs py-0.5" @change="save('format', local.format)">
          <option value="shorts_10s">10s Short</option>
          <option value="shorts_30s">30s Short</option>
        </select>
      </template>
      <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
        {{ timeAgo(concept.created_at) }}
      </span>
    </div>

    <!-- Scene summary (view) / scene editor (edit) -->
    <div class="space-y-1.5">
      <template v-if="!editing">
        <p
          v-for="s in local.scene_structure?.slice(0, 2)"
          :key="s.scene"
          class="text-xs text-sekai-subtle leading-relaxed"
        >
          <span class="text-sekai-muted">{{ s.scene }}.</span> {{ s.description }}
        </p>
      </template>
      <template v-else>
        <div v-for="(s, i) in local.scene_structure" :key="s.scene" class="space-y-0.5">
          <p class="text-xs text-sekai-muted">Scene {{ s.scene }}</p>
          <textarea
            v-model="local.scene_structure[i].description"
            class="textarea text-xs"
            rows="2"
            @blur="save('scene_structure', local.scene_structure)"
          />
        </div>
      </template>
    </div>

    <!-- Image prompt (only visible in edit mode) -->
    <div v-if="editing" class="space-y-0.5">
      <p class="label">Image Prompt</p>
      <textarea
        v-model="local.image_prompt"
        class="textarea text-xs"
        rows="4"
        @blur="save('image_prompt', local.image_prompt)"
      />
    </div>

    <!-- Video motion instruction (only visible in edit mode) -->
    <div v-if="editing" class="space-y-0.5">
      <p class="label">Video Motion</p>
      <textarea
        v-model="local.video_motion_instruction"
        class="textarea text-xs"
        rows="2"
        @blur="save('video_motion_instruction', local.video_motion_instruction)"
      />
    </div>

    <!-- Audio mood -->
    <div class="border-t border-sekai-border pt-2.5 mt-0.5">
      <p v-if="!editing" class="text-xs text-sekai-subtle italic">"{{ local.audio_mood }}"</p>
      <div v-else class="space-y-0.5">
        <p class="label">Audio Mood</p>
        <textarea
          v-model="local.audio_mood"
          class="textarea text-xs"
          rows="2"
          @blur="save('audio_mood', local.audio_mood)"
        />
      </div>
    </div>

    <!-- Save feedback -->
    <p v-if="saveMsg" class="text-xs text-sekai-accent -mt-1">{{ saveMsg }}</p>

    <!-- Actions -->
    <div class="flex gap-2 mt-1">
      <template v-if="concept.status === 'pending_approval'">
        <button class="btn-primary flex-1 text-xs py-1.5" @click="$emit('approve')">Approve</button>
        <button class="btn-danger flex-1 text-xs py-1.5" @click="$emit('reject')">Reject</button>
      </template>
      <template v-else-if="concept.status !== 'rejected'">
        <button class="btn-ghost flex-1 text-xs py-1.5" @click="$emit('review')">
          {{ concept.status === 'uploaded' ? 'View' : 'Continue →' }}
        </button>
      </template>
      <template v-else>
        <span class="text-xs text-sekai-error flex-1 text-center py-1.5">Rejected</span>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({ concept: Object })
const emit  = defineEmits(['approve', 'reject', 'review', 'refresh'])

// Deep-copy concept into local reactive state so edits are isolated
const local = reactive(JSON.parse(JSON.stringify(props.concept)))
watch(() => props.concept, (c) => Object.assign(local, JSON.parse(JSON.stringify(c))))

const editing = ref(false)
const saveMsg = ref('')

// Edit allowed before image generation starts
const canEdit = props.concept.status === 'pending_approval' || props.concept.status === 'approved'

let _saveTimer = null
async function save(field, value) {
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(async () => {
    try {
      const r = await fetch(`/api/concepts/${props.concept.id}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ [field]: value }),
      })
      if (!r.ok) throw new Error((await r.json()).detail)
      saveMsg.value = 'Saved'
      setTimeout(() => { saveMsg.value = '' }, 1500)
      emit('refresh')
    } catch (e) {
      saveMsg.value = `Error: ${e.message}`
    }
  }, 300)
}

function timeAgo(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
</script>
