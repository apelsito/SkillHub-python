import type { NotificationItem } from '@/api/types'

export type NotificationDisplay = {
  title: string
  description: string
}

type NotificationBody = {
  skillName?: string
  version?: string
}

function parseBody(bodyJson?: string): NotificationBody {
  if (!bodyJson) {
    return {}
  }
  try {
    const parsed = JSON.parse(bodyJson)
    return typeof parsed === 'object' && parsed !== null ? parsed as NotificationBody : {}
  } catch {
    return {}
  }
}

export function resolveNotificationDisplay(item: NotificationItem, _language = 'en'): NotificationDisplay {
  const body = parseBody(item.bodyJson)
  const skillName = body.skillName ?? ''
  const version = body.version ?? ''
  const versionSuffix = version ? ` (${version})` : ''

  switch (item.eventType) {
    case 'REVIEW_SUBMITTED':
      return {
        title: 'Review submitted',
        description: skillName ? `${skillName}${versionSuffix} was submitted for review.` : '',
      }
    case 'REVIEW_APPROVED':
      return {
        title: 'Review approved',
        description: skillName ? `${skillName}${versionSuffix} was approved.` : '',
      }
    case 'REVIEW_REJECTED':
      return {
        title: 'Review rejected',
        description: skillName ? `${skillName}${versionSuffix} was rejected.` : '',
      }
    case 'PROMOTION_SUBMITTED':
      return {
        title: 'Promotion submitted',
        description: skillName ? `${skillName}${versionSuffix} was submitted for promotion.` : '',
      }
    case 'PROMOTION_APPROVED':
      return {
        title: 'Promotion approved',
        description: skillName ? `${skillName}${versionSuffix} promotion was approved.` : '',
      }
    case 'PROMOTION_REJECTED':
      return {
        title: 'Promotion rejected',
        description: skillName ? `${skillName}${versionSuffix} promotion was rejected.` : '',
      }
    case 'REPORT_SUBMITTED':
      return {
        title: 'Report submitted',
        description: skillName ? `${skillName} received a new report.` : '',
      }
    case 'REPORT_RESOLVED':
      return {
        title: 'Report resolved',
        description: skillName ? `${skillName} report has been resolved.` : '',
      }
    case 'SKILL_PUBLISHED':
      return {
        title: 'Skill published',
        description: skillName ? `${skillName}${versionSuffix} was published.` : '',
      }
    case 'SUBSCRIPTION_NEW_VERSION':
      return {
        title: 'Subscribed skill updated',
        description: skillName ? `${skillName}${versionSuffix} published a new version.` : '',
      }
    case 'SUBSCRIPTION_VERSION_YANKED':
      return {
        title: 'Subscribed skill version yanked',
        description: skillName ? `${skillName}${versionSuffix} version was yanked.` : '',
      }
    default:
      return {
        title: item.title,
        description: '',
      }
  }
}
