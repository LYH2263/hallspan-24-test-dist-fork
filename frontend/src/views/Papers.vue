<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/papers') })
</script>
<template>
  <h1>试卷套</h1>
  <p class="sub">顶部纸套标签对应的试卷版本</p>
  <div class="hs-tabs" style="margin-bottom:1rem;background:transparent">
    <span
      v-for="(r,i) in rows" :key="r.id ?? JSON.stringify(r)"
      class="hs-tabs"
      style="display:inline-block"
    >
      <span
        style="display:inline-block;padding:0.45rem 0.9rem;background:var(--hs-clip);border:1px solid #b0a890;border-radius:6px 6px 0 0;margin-right:0.25rem;font-family:Segoe UI,PingFang SC,sans-serif;font-size:0.85rem"
      >{{ r.code }} · {{ r.title }}</span>
    </span>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)"><td>{{ r.code }}</td><td>{{ r.title }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
