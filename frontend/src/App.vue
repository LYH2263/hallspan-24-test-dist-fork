<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>
<template>
  <div class="hs-exam">
    <header class="hs-paper-tabs">
      <div class="hs-brand">HallSpan · 考场排座</div>
      <nav class="hs-tabs">
        <RouterLink to="/map">排座图</RouterLink>
        <RouterLink to="/papers">试卷套 A/B</RouterLink>
        <RouterLink to="/candidates">考生名册</RouterLink>
        <RouterLink to="/violations">违规</RouterLink>
        <RouterLink to="/halls">考室</RouterLink>
        <RouterLink to="/stats">统计</RouterLink>
      </nav>
    </header>
    <div class="hs-workspace">
      <RouterView />
    </div>
  </div>
</template>
