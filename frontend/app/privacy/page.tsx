import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { type LegalSection } from "@/components/LegalPage";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `How ${LEGAL.brand} collects, uses, shares and protects personal data from reviewers, website visitors and people who appear in video reviews.`,
};

const B = LEGAL.brand;

const sections: LegalSection[] = [
  {
    id: "scope",
    title: "Who we are and what this policy covers",
    body: (
      <>
        <p>
          {LEGAL.operator} (<strong>{B}</strong>, <strong>we</strong>, <strong>us</strong>) operates the {B} website at{" "}
          <a href={LEGAL.siteUrl}>{LEGAL.siteUrl}</a>, the {B} WhatsApp submission service and the related API (together, the{" "}
          <strong>Service</strong>). We are the data controller for the personal data described in this policy.
        </p>
        <p>This policy applies to four groups of people:</p>
        <ul>
          <li><strong>Reviewers</strong>, who send us a link to their public Instagram reel over WhatsApp;</li>
          <li><strong>People who appear in reels</strong> but did not submit them, such as friends or staff visible or audible in a video;</li>
          <li><strong>Business owners and staff</strong>, where a listed business is a sole trader or its name identifies a person, or where you contact us about a listing;</li>
          <li><strong>Website and API visitors</strong>.</li>
        </ul>
        <p>
          It does not cover Instagram, WhatsApp, Google Maps or any other third-party service you use alongside {B}. Their own privacy
          policies apply. Our <Link href="/terms">Terms of Service</Link> govern use of the Service.
        </p>
      </>
    ),
  },
  {
    id: "data",
    title: "The personal data we collect",
    body: (
      <>
        <h3>From reviewers, over WhatsApp</h3>
        <ul>
          <li>Your WhatsApp phone number and the profile name WhatsApp shares with businesses;</li>
          <li>The messages you send us, including the reel link, any clarifications we ask for (for example, which of two similarly named businesses you meant), and the time of each message;</li>
          <li>Messages we send you, and delivery status.</li>
        </ul>
        <h3>From your public Instagram reel</h3>
        <ul>
          <li>The video and its audio track, which we download and keep a working copy of;</li>
          <li>Your image and voice as they appear in the video;</li>
          <li>Your Instagram username and display name, the caption, the post date, and the reel&rsquo;s public URL and shortcode.</li>
        </ul>
        <h3>Data we derive by processing the reel</h3>
        <ul>
          <li>A result of our talking-face check (whether a person is visibly speaking on camera; see section 5);</li>
          <li>A transcript of what is said, and the language detected;</li>
          <li>Structured review fields: the business named, when and where the visit happened as you describe it, what was good, what could improve, whether you recommend the business, category, keywords, a one-line summary and a sentiment label;</li>
          <li>Per-business aggregates, such as the recommendation rate and the AI summary, which combine your review with others.</li>
        </ul>
        <h3>From website and API visitors</h3>
        <ul>
          <li>Standard server and content-delivery logs: IP address, approximate location derived from it, browser and device type, the pages and API endpoints requested, referring page, and timestamps;</li>
          <li>Your search queries, which are sent to our API to return results. They are logged in aggregate for debugging and are not linked to an account (we have none).</li>
        </ul>
        <h3>From businesses and people who contact us</h3>
        <ul>
          <li>Business names, addresses, categories, map coordinates and Google place identifiers, obtained from Google&rsquo;s Places API or from the reviewer&rsquo;s description;</li>
          <li>Your name, email address, role and the content of your message when you email us or send a takedown notice.</li>
        </ul>
        <p>
          We do not collect payment information, government identifiers, or precise device location. We do not ask reviewers for their
          age, address or any information beyond the reel link, but what you say in the video is up to you.
        </p>
      </>
    ),
  },
  {
    id: "sources",
    title: "Where the data comes from",
    body: (
      <ul>
        <li><strong>Directly from you</strong>, when you message our WhatsApp number or email us;</li>
        <li><strong>From Instagram</strong>, by fetching the public reel at the link you give us. We can only process reels that are public; private content is rejected without being stored;</li>
        <li><strong>From Google</strong>, when we look up the business you named to confirm its identity and location;</li>
        <li><strong>Generated by us</strong>, through the automated processing described in sections 5 and 6;</li>
        <li><strong>Automatically</strong>, through server logs when you visit the website or call the API.</li>
      </ul>
    ),
  },
  {
    id: "purposes",
    title: "How we use personal data and our legal bases",
    body: (
      <>
        <p>
          We rely on the legal bases set out in the Nigeria Data Protection Act 2023 and, where they apply to you, the EU and UK General
          Data Protection Regulation and other data-protection laws in the countries we serve.
        </p>
        <ul>
          <li>
            <strong>To receive, verify and publish your review</strong>, including downloading the reel, checking that a person is speaking,
            transcribing it, extracting the review, publishing it on the business page with the embedded reel and your display name, and
            messaging you about the outcome. <em>Basis:</em> your consent, given when you send us the link, and performance of the agreement in
            our Terms.
          </li>
          <li>
            <strong>To generate and update AI summaries and aggregate statistics</strong> for each business. <em>Basis:</em> our legitimate
            interest in making reviews useful and comparable, balanced against the fact that the underlying reviews are already public.
          </li>
          <li>
            <strong>To ask you clarifying questions</strong> over WhatsApp. <em>Basis:</em> performance of the agreement in our Terms.
          </li>
          <li>
            <strong>To prevent fraud, spam and abuse</strong>, such as detecting coordinated campaigns, duplicate submissions or attempts to
            manipulate our models. <em>Basis:</em> legitimate interest in the integrity of the Service.
          </li>
          <li>
            <strong>To operate, secure and improve the website and API</strong>, including debugging, capacity planning and measuring which
            features are used, using logs and aggregate query data. <em>Basis:</em> legitimate interest.
          </li>
          <li>
            <strong>To respond to your requests, complaints and takedown notices</strong>, and to resolve disputes between reviewers and
            businesses. <em>Basis:</em> legitimate interest and, where applicable, legal obligation.
          </li>
          <li>
            <strong>To comply with law</strong>, including responding to lawful requests from authorities and defending legal claims.{" "}
            <em>Basis:</em> legal obligation and legitimate interest.
          </li>
        </ul>
        <p>
          We do not use personal data for advertising, we do not sell it, and we do not build profiles of reviewers or visitors for any
          purpose other than abuse prevention.
        </p>
      </>
    ),
  },
  {
    id: "face-voice",
    title: "Processing of your face and voice",
    body: (
      <>
        <p>
          A core promise of {B} is that reviews come from real people on camera. To check this, we send frames from your reel to Meta&rsquo;s
          SAM 3.1 model, which detects whether a person is present and visibly speaking during the video. The output we keep is a pass or fail
          result and a confidence score.
        </p>
        <p>
          <strong>We do not perform facial recognition.</strong> We do not create a face template or voiceprint, we do not attempt to
          identify you or match you against any database, and we do not compare faces across reviews to work out whether two reviews are
          from the same person. Your image and voice are processed only to confirm that a person is speaking and to transcribe what is said.
        </p>
        <p>
          Your voice is transcribed by Meta&rsquo;s Muse Voice Transcribe model, and the transcript is processed by Muse Spark to extract the
          review. These models are accessed through Meta&rsquo;s API under terms that prohibit Meta from using our inputs to train its models.
          We do not use your face, voice or transcript to train machine learning models of our own.
        </p>
        <p>
          In some countries, images of faces and recordings of voices are treated as special or sensitive categories of personal data. Where
          that applies, our basis for processing them is your explicit consent, given when you submit a reel that you have already chosen to
          make public. You can withdraw consent at any time by asking us to remove your review (section 11).
        </p>
      </>
    ),
  },
  {
    id: "automated",
    title: "Automated decisions and AI output",
    body: (
      <>
        <p>
          Whether a submitted reel is accepted or rejected is decided automatically, without a person reviewing it, based on the checks
          described above and on content rules in our Terms. Transcripts, review fields, sentiment labels and summaries are also generated
          automatically and may contain errors.
        </p>
        <p>
          If a submission is rejected, we tell you why over WhatsApp. If you think a decision or an AI output is wrong, reply on WhatsApp or
          email <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>. A person will review it, and you can give us your point of
          view. We will correct or remove outputs that misrepresent what you said.
        </p>
      </>
    ),
  },
  {
    id: "sharing",
    title: "Who we share personal data with",
    body: (
      <>
        <h3>Publicly</h3>
        <p>
          When your review is published, the following are visible to anyone: your Instagram display name, the embedded reel (served by
          Instagram), the transcript-derived review fields, the sentiment label, the language, and the date. Your{" "}
          <strong>WhatsApp phone number is never published</strong> and is never shared with the business you reviewed.
        </p>
        <h3>Service providers (processors)</h3>
        <p>These companies process personal data on our behalf under contracts that restrict their use of it:</p>
        <ul>
          <li><strong>Meta Platforms</strong>: the WhatsApp Business Cloud API carries your messages to us; Meta&rsquo;s model API runs the face check, transcription and extraction on video frames, audio and text we send it;</li>
          <li><strong>Amazon Web Services</strong>: hosts our website, API, database, search index and stored media;</li>
          <li>
            <strong>Google</strong>: resolves business names to places through the Places API. We send the business name and area, not
            your personal data. When a business page shows Google reviews, that review content (reviewer names, ratings and text) is
            fetched live from Google Places each time the page loads and is not stored by us; we cache only the Google place
            identifier and an AI-generated summary of those reviews, for up to 24 hours;
          </li>
          <li><strong>Instagram</strong>: we fetch your public reel from Instagram, and the business page embeds it from Instagram&rsquo;s servers, which means Instagram learns that a visitor loaded that embed.</li>
        </ul>
        <h3>Others</h3>
        <ul>
          <li><strong>Businesses and complainants</strong>: if a business sends a takedown notice about your review, we may share the substance of their complaint with you and, if you respond, your response with them, without revealing your phone number;</li>
          <li><strong>Authorities and legal process</strong>: where required by law, court order or to protect the rights, safety or property of {B}, our users or the public;</li>
          <li><strong>A successor</strong>: if {B} is acquired or merges, personal data may transfer to the new operator under this policy; we will notify reviewers over WhatsApp or on the website.</li>
        </ul>
        <p>Our source code is open source, but no personal data is included in the public repository.</p>
      </>
    ),
  },
  {
    id: "transfers",
    title: "International transfers",
    body: (
      <>
        <p>
          Our infrastructure runs on Amazon Web Services in the United States (us-east-1 region). Meta and Google process data in the United
          States and other countries where they operate. This means personal data collected in Nigeria and other African countries, and from
          visitors elsewhere, is transferred internationally.
        </p>
        <p>
          Where the destination country has not been recognised as providing adequate protection, we rely on contractual safeguards,
          including data-processing terms and standard contractual clauses offered by these providers, and on your consent to publication of
          content you have already made public worldwide on Instagram. You can ask us for more information about these safeguards at{" "}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>.
        </p>
      </>
    ),
  },
  {
    id: "cookies",
    title: "Cookies and similar technologies",
    body: (
      <>
        <p>
          <strong>Our website sets no cookies</strong> and uses no third-party analytics, advertising or tracking pixels. It stores nothing in your
          browser other than what your browser caches to load pages faster.
        </p>
        <p>
          Business pages embed Instagram reels using Instagram&rsquo;s official embed script. When an embed loads, Instagram (Meta) may set
          cookies and collect data about your visit under its own <a href="https://privacycenter.instagram.com/policy" target="_blank" rel="noreferrer">privacy policy</a>{" "}
          and <a href="https://www.instagram.com/legal/cookies/" target="_blank" rel="noreferrer">cookie policy</a>, whether or not you are logged in
          to Instagram. If you prefer not to load Instagram content, each review has an &ldquo;Open on Instagram&rdquo; link you can use instead,
          and you can block third-party cookies in your browser.
        </p>
        <p>If we introduce analytics or other cookies in future, we will update this policy and, where the law requires it, ask for your consent first.</p>
      </>
    ),
  },
  {
    id: "retention",
    title: "How long we keep personal data",
    body: (
      <>
        <ul>
          <li><strong>Published reviews</strong> (review fields, transcript, display name, reel link) are kept for as long as the review is published, and deleted within 30 days of your withdrawal request or of our removing the review;</li>
          <li><strong>Our stored copy of your video and audio</strong> is kept while the review is published, so that we can re-run the pipeline when our models improve, and deleted within 30 days of withdrawal or removal;</li>
          <li><strong>Rejected or abandoned submissions</strong>, including any downloaded media, are deleted within 30 days;</li>
          <li><strong>WhatsApp conversations</strong> are kept for 12 months after the last message, so that we can handle follow-up questions and withdrawal requests from the same number, then deleted. We keep a hashed form of your phone number for a further 12 months only to enforce blocks for abuse;</li>
          <li><strong>Aggregates</strong> such as a business&rsquo;s recommendation rate and AI summary may continue to reflect a withdrawn review&rsquo;s vote until the summary is next regenerated, which happens on the next review for that business or within 30 days, whichever is sooner. Aggregates do not identify you;</li>
          <li><strong>Server and access logs</strong> are kept for 90 days;</li>
          <li><strong>Emails, complaints and takedown notices</strong> are kept for 3 years after the matter is closed, to document how it was handled;</li>
          <li><strong>Backups</strong> are retained for up to 35 days and then overwritten; data deleted from live systems disappears from backups on that cycle.</li>
        </ul>
        <p>We may keep data longer where we must by law or to establish, exercise or defend legal claims.</p>
      </>
    ),
  },
  {
    id: "rights",
    title: "Your rights and how to exercise them",
    body: (
      <>
        <p>Depending on where you live, you have some or all of the following rights, and we honour them for everyone regardless of location:</p>
        <ul>
          <li><strong>Access</strong>: ask for a copy of the personal data we hold about you;</li>
          <li><strong>Rectification</strong>: ask us to correct inaccurate data, including a transcript or extracted field that misrepresents what you said;</li>
          <li><strong>Erasure</strong>: ask us to remove your review and delete your data;</li>
          <li><strong>Restriction and objection</strong>: ask us to pause processing or object to processing based on legitimate interests;</li>
          <li><strong>Portability</strong>: receive the data you provided in a machine-readable format;</li>
          <li><strong>Withdraw consent</strong> at any time, without affecting processing that already took place;</li>
          <li><strong>Not be subject to a solely automated decision</strong> with significant effects without human review, which you can request under section 6.</li>
        </ul>
        <p>
          <strong>To exercise a right</strong>, message the {B} WhatsApp number from the phone number you submitted with, or email{" "}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>. To protect you, we verify requests: for WhatsApp we rely on the
          sending number; for email we may ask you to confirm from the Instagram account that posted the reel. We respond within 30 days,
          extendable once by a further 30 days for complex requests, and we will tell you if we extend. We do not charge for requests unless
          they are manifestly unfounded or excessive.
        </p>
        <p>
          <strong>Complaints.</strong> If you are unhappy with how we handle your data, please contact us first. You also have the right to
          complain to a supervisory authority: in Nigeria, the Nigeria Data Protection Commission (NDPC); in the EU or UK, your national
          data-protection authority; elsewhere, the authority responsible for data protection in your country.
        </p>
      </>
    ),
  },
  {
    id: "bystanders",
    title: "If you appear in a reel you did not submit",
    body: (
      <>
        <p>
          Reviewers must have the consent of anyone who appears in their video, but we cannot verify this. If you appear in or are audible in a
          reel published on {B} and did not agree to it, email <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a> with the
          business page link and a description of where you appear. We will remove the review from {B} within 14 days unless the reviewer can
          show your consent, and we will tell the reviewer that a complaint was made without revealing your identity unless you agree.
        </p>
        <p>
          We cannot remove the reel from Instagram itself; for that, use Instagram&rsquo;s reporting tools.
        </p>
      </>
    ),
  },
  {
    id: "businesses",
    title: "Business owners and staff",
    body: (
      <>
        <p>
          Information about businesses (name, address, category, location) is generally not personal data. Where a business is a sole trader,
          or staff are named or shown in a review, that information is personal data and this policy applies. We publish it on the basis of
          our legitimate interest in providing a public review service about businesses that offer goods and services to the public, and of
          the reviewer&rsquo;s freedom of expression.
        </p>
        <p>
          You may object to the processing of data about you by emailing <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a>. We
          will weigh your objection against these interests and respond within 30 days. Honest reviews of a business are not removed solely
          because the business objects; see our Terms for how to raise concerns about a specific review.
        </p>
      </>
    ),
  },
  {
    id: "security",
    title: "Security",
    body: (
      <p>
        We protect personal data with technical and organisational measures appropriate to the risk, including encryption in transit (TLS)
        and at rest, access controls limited to staff who need access, private storage for downloaded media, secret management for API
        credentials, logging of administrative access, and verification of WhatsApp webhook signatures. No system is perfectly secure. If we
        become aware of a breach that is likely to affect your rights, we will notify you and the relevant authority as required by law,
        which in Nigeria means notifying the NDPC within 72 hours.
      </p>
    ),
  },
  {
    id: "children",
    title: "Children",
    body: (
      <p>
        The Service is not directed at children. You must be at least {LEGAL.minimumAge} to submit a review. We do not knowingly collect
        personal data from anyone under {LEGAL.minimumAge}. If you believe a reviewer is under {LEGAL.minimumAge}, or a child appears in a
        reel without parental consent, email <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a> and we will remove the
        content promptly.
      </p>
    ),
  },
  {
    id: "changes",
    title: "Changes to this policy",
    body: (
      <p>
        We will update this policy as the Service evolves, for example if we change the models we use, add analytics, or expand to new
        countries. We will post the new version here with a new effective date. For changes that materially affect how we use your personal
        data, we will also notify reviewers over WhatsApp or by a prominent notice on the website before the change takes effect.
      </p>
    ),
  },
  {
    id: "contact",
    title: "Contact",
    body: (
      <p>
        {LEGAL.operator}
        <br />
        {LEGAL.address}
        <br />
        Privacy requests and questions: <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>
        <br />
        Legal and takedown notices: <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a>
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      kicker="Legal"
      title="Privacy Policy"
      effective={LEGAL.privacyEffective}
      related={{ href: "/terms", label: "Terms of Service" }}
      intro={
        <p>
          {B} turns public Instagram reels into structured business reviews. That involves processing video of people&rsquo;s faces and
          recordings of their voices, so we want to be clear about exactly what we collect, what we do with it, who sees it, and how you can
          control it.
        </p>
      }
      summary={[
        "We collect your WhatsApp number and messages, your public reel (video, audio, username), and the transcript and review we extract from it.",
        "We check that a real person is speaking on camera. We do not do facial recognition, create face or voice templates, or identify you.",
        "Your Instagram display name and the review are public. Your phone number is never published or shared with the business.",
        "Processing is done by Meta's models and hosted on AWS in the United States. Nothing is sold and nothing is used for advertising.",
        "Our website sets no cookies. Embedded Instagram reels are served by Instagram under Meta's cookie policy.",
        "You can withdraw a review and have your data deleted at any time, from the WhatsApp number you used or by email. We respond within 30 days.",
        "People who appear in a reel without consenting, and businesses, can ask us to act by email.",
      ]}
      sections={sections}
    />
  );
}
