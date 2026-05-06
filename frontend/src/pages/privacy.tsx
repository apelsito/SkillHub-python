import { LegalDocument } from '@/shared/components/legal-document'

const privacyDocument = {
  eyebrow: 'Legal',
  title: 'Privacy Policy',
  summary: 'This policy explains how SkillHub collects, uses, shares, and protects information when we provide skill registry, publishing, review, download, account, and related API services.',
  lastUpdated: 'Last updated: March 14, 2026',
  note: 'If you use a privately deployed SkillHub instance, that deployment operator may also process data under its own internal policies and may act independently for data handled in that environment.',
  sections: [
    {
      title: '1. Scope',
      paragraphs: [
        'This policy applies to the SkillHub website, web console, public skill pages, login flows, device authorization flows, and related APIs and services.',
        'When you browse skills, publish versions, participate in reviews, create tokens, or download content, this policy describes how we handle information related to you.',
      ],
    },
    {
      title: '2. Information We Collect',
      paragraphs: [],
      bullets: [
        'Account and identity information such as username, email, avatar, OAuth provider identifiers, platform roles, and namespace membership.',
        'Content you submit, including skill packages, README files, release notes, namespace profiles, ratings, stars, and review comments.',
        'Usage and security information such as IP address, browser or device details, request logs, download activity, login events, API token metadata, error logs, and audit logs.',
      ],
    },
    {
      title: '3. How We Use Information',
      paragraphs: [],
      bullets: [
        'To provide login, session management, access control, device authorization, account security, and basic support.',
        'To display public skill pages and power search, downloads, ratings, stars, namespace collaboration, and governance workflows.',
        'To perform review operations, rate limiting, abuse prevention, debugging, performance analysis, and service improvement.',
        'To send important notices related to security, policy changes, or service availability when needed.',
      ],
    },
    {
      title: '4. Public Information and Sharing',
      paragraphs: [
        'Skills you publish publicly, release notes, namespace names, public ratings, and some profile information may be visible to other users or visitors.',
        'We do not sell personal information. We may share information when necessary to provide hosting, authentication, monitoring, or compliance support, or to comply with law and protect the service and its users.',
        'For private deployments, the instance operator may also access, process, or retain data according to its own internal governance and compliance requirements.',
      ],
    },
    {
      title: '5. Data Retention and Choices',
      paragraphs: [
        'We retain account information, skill metadata, review records, and security logs for as long as needed to operate the service and may retain them longer where required for legal, audit, or compliance purposes.',
        'You can update account information, change your password, and revoke or recreate API tokens. You can contact the instance administrator to request export, correction, or deletion of information related to you, although some records may need to be retained for security, audit, or compliance reasons.',
      ],
    },
    {
      title: '6. Security and Contact',
      paragraphs: [
        'We use reasonable technical and organizational safeguards such as access controls, authentication, auditing, token management, and transport security.',
        'No internet service can guarantee absolute security. Protect your credentials and report suspicious access, leakage, or misuse promptly to the instance operator.',
        'If you need to contact us, use the documentation, community, support channel, or administrator contact information provided by the current SkillHub instance.',
      ],
    },
  ],
} as const

export function PrivacyPolicyPage() {
  return <LegalDocument {...privacyDocument} />
}
