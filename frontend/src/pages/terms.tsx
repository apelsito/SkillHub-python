import { LegalDocument } from '@/shared/components/legal-document'

const termsDocument = {
  eyebrow: 'Legal',
  title: 'Terms of Service',
  summary: 'These terms apply to your access to and use of SkillHub for browsing, publishing, reviewing, downloading, account management, and related API services. By using the service, you agree to these terms.',
  lastUpdated: 'Last updated: March 14, 2026',
  note: 'If your organization runs a private SkillHub deployment, it may impose additional internal rules, information security requirements, or acceptable use policies on top of these baseline terms.',
  sections: [
    {
      title: '1. Acceptance and Scope',
      paragraphs: [
        'By accessing, registering for, or using SkillHub, you agree to these Terms of Service, the related Privacy Policy, and any operating rules for the current instance.',
        'If you use SkillHub on behalf of a team, company, or other organization, you represent that you have authority to accept these terms on its behalf.',
      ],
    },
    {
      title: '2. Accounts and Access Security',
      paragraphs: [],
      bullets: [
        'You must provide accurate and current account information and protect your credentials, OAuth sessions, and API tokens.',
        'You are responsible for activity performed through your account, including publishing, reviewing, downloading, token generation, and namespace administration.',
        'If you become aware of unauthorized access, credential leakage, or another security incident, promptly notify the instance administrator or operator.',
      ],
    },
    {
      title: '3. Skills, Namespaces, and User Content',
      paragraphs: [
        'You retain rights in content you upload or submit, but you grant SkillHub a non-exclusive worldwide license to host, store, copy, process, display, and distribute that content as needed to operate the service.',
        'You are responsible for the skill packages, README files, descriptions, screenshots, review comments, and other materials you submit, and you represent that you have the right to provide them.',
      ],
      bullets: [
        'Do not upload malware, unlawful material, infringing material, deceptive material, or content intended to mislead users.',
        'Do not impersonate others, take namespaces without authorization, or attempt to bypass review, moderation, or access controls.',
        'When downloading or redistributing a skill, comply with that skill package license terms, third-party dependency licenses, and applicable law.',
      ],
    },
    {
      title: '4. Review, Governance, and Enforcement',
      paragraphs: [
        'SkillHub may review content and may approve, reject, hide, remove, yank versions, restrict access, or suspend accounts to protect service security, compliance, and quality.',
        'Where abuse, infringement, security risk, unlawful conduct, or other violations are suspected, the platform or instance administrator may preserve logs and take appropriate action.',
      ],
    },
    {
      title: '5. Downloads, APIs, and Acceptable Use',
      paragraphs: [],
      bullets: [
        'You may not interfere with service stability or bypass authentication, rate limits, security controls, or authorization boundaries.',
        'You may not scrape, stress test, scan, or automate against SkillHub in a destructive manner, or use the service to distribute malicious payloads.',
        'Skills downloaded through SkillHub are provided by their publishers and are used subject to their own licenses and risk notices.',
      ],
    },
    {
      title: '6. Availability and Liability',
      paragraphs: [
        'We may modify, update, limit, or discontinue parts of the service at any time, including search, downloads, review workflows, login methods, and API capabilities.',
        'To the maximum extent permitted by law, SkillHub is provided as is and as available without express or implied warranties. SkillHub and its operators will not be liable for indirect, incidental, special, consequential, or punitive damages.',
      ],
    },
    {
      title: '7. Termination, Changes, and Contact',
      paragraphs: [
        'You may stop using SkillHub at any time. We may suspend or terminate access if you violate these terms, create security risk, or if required by law.',
        'We may update these terms from time to time. Your continued use after an update means you accept the revised version. Use the documentation, community, or administrator channel provided by the current instance for contact.',
      ],
    },
  ],
} as const

export function TermsOfServicePage() {
  return <LegalDocument {...termsDocument} />
}
