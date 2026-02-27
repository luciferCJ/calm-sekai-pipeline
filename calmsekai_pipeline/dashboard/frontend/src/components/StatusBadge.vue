<template>
  <span :class="badgeClass">{{ label }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ status: String })

const STATUS_MAP = {
  pending_approval: { cls: 'badge-pending',  label: 'Pending'       },
  approved:         { cls: 'badge-approved', label: 'Approved'      },
  rejected:         { cls: 'badge-rejected', label: 'Rejected'      },
  image_done:       { cls: 'badge-done',     label: 'Image ready'   },
  video_done:       { cls: 'badge-done',     label: 'Video ready'   },
  assembly_done:    { cls: 'badge-done',     label: 'Assembled'     },
  seo_done:         { cls: 'badge-done',     label: 'SEO done'      },
  uploaded:         { cls: 'badge-uploaded', label: 'Uploaded ✓'    },
}

const badgeClass = computed(() => STATUS_MAP[props.status]?.cls ?? 'badge-pending')
const label      = computed(() => STATUS_MAP[props.status]?.label ?? props.status)
</script>
