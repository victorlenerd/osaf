import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { type LegalSection } from "@/components/LegalPage";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: `The terms that govern use of ${LEGAL.brand}, including how video reviews are submitted, verified, published and removed.`,
};

const B = LEGAL.brand;

const sections: LegalSection[] = [
  {
    id: "agreement",
    title: "Agreement to these Terms",
    body: (
      <>
        <p>
          These Terms of Service (the <strong>Terms</strong>) are a binding agreement between you and {LEGAL.operator}{" "}
          (<strong>{B}</strong>, <strong>we</strong>, <strong>us</strong>) and govern your access to and use of the {B} website at{" "}
          <a href={LEGAL.siteUrl}>{LEGAL.siteUrl}</a>, the {B} WhatsApp submission service, our application programming interface, and any
          related content, features or services (together, the <strong>Service</strong>).
        </p>
        <p>
          By browsing the website, sending a message to the {B} WhatsApp number, or otherwise using the Service, you accept these
          Terms and our <Link href="/privacy">Privacy Policy</Link>, which is incorporated by reference. If you do not agree, do not use
          the Service.
        </p>
        <p>
          If you use the Service on behalf of a business or other organisation, you represent that you have authority to bind that
          organisation, and &ldquo;you&rdquo; includes it.
        </p>
      </>
    ),
  },
  {
    id: "eligibility",
    title: "Eligibility",
    body: (
      <>
        <p>
          You must be at least {LEGAL.minimumAge} years old, or the age of majority where you live if that is higher, to submit a review or
          otherwise contribute content. Anyone may browse published content. By submitting content you confirm that you meet this
          requirement and that you are not barred from using the Service under any applicable law.
        </p>
        <p>
          You must also hold an Instagram account and a WhatsApp account in your own name that comply with Meta&rsquo;s terms. We do not
          control those platforms and are not responsible for your access to them.
        </p>
      </>
    ),
  },
  {
    id: "service",
    title: "What the Service is",
    body: (
      <>
        <p>
          {B} is a discovery platform for video reviews of businesses, with a focus on Africa. Reviewers record themselves talking about
          a business, post the video publicly as an Instagram reel, and send us the link over WhatsApp. Our automated pipeline checks that
          the reel is public and shows a person speaking on camera, transcribes what is said, extracts a structured review (the business,
          the visit, what was good, what could improve, and whether the reviewer recommends it), and publishes it on the business&rsquo;s
          page together with an embedded copy of the reel. For each business we also generate and periodically regenerate an{" "}
          <strong>AI summary</strong> of all its reviews.
        </p>
        <p>
          The Service is informational. We are not a party to any dealing between you and a business listed on {B}, we do not endorse any
          business or reviewer, and we do not verify the accuracy of opinions expressed in reviews.
        </p>
      </>
    ),
  },
  {
    id: "submitting",
    title: "Submitting a review",
    body: (
      <>
        <p>When you send us a reel link you make the following commitments, each of which is a condition of publication:</p>
        <ul>
          <li>
            <strong>It is your reel.</strong> You created the video, you appear in it or have the clear consent of everyone who does, and you
            posted it from an Instagram account you control.
          </li>
          <li>
            <strong>It is a genuine, first-hand experience.</strong> You personally visited or dealt with the business you are reviewing, on or
            around the date you describe.
          </li>
          <li>
            <strong>It is honest.</strong> You believe what you say to be true. You will not fabricate, exaggerate for effect, or review a
            business you have not used.
          </li>
          <li>
            <strong>You disclose material connections.</strong> If you own, work for, are related to, compete with, or were paid, gifted or
            otherwise incentivised by the business (or a competitor) in connection with the review, you must say so clearly in the video. We
            may decline or remove reviews that appear to be undisclosed advertising or coordinated.
          </li>
          <li>
            <strong>It is public and stays public.</strong> We can only process public reels. If you later make the reel private or delete it,
            the embedded video will stop displaying and we may remove the review.
          </li>
          <li>
            <strong>It is about the business.</strong> Reviews must concern the goods, services, premises or conduct of the business.
            Content that targets private individuals, discloses personal information of others, or is unrelated to the business is not
            permitted.
          </li>
          <li>
            <strong>It complies with the law and the Content Rules</strong> in section 6.
          </li>
        </ul>
        <p>
          Submission is free. We do not pay for reviews and no business may pay you through us. To keep reviews genuine, each person
          may publish at most three reviews in any rolling seven-day period, and we may limit the number of reviews one person may
          submit for the same business. We may ask you clarifying questions over WhatsApp (for example, which of two similarly named
          businesses you meant) before publishing.
        </p>
        <p>
          <strong>Points.</strong> Each published review earns a fixed number of Afefehub points as a thank-you. Points are awarded in
          the same amount for every published review whether it is positive, mixed or negative, so they never reward a particular
          opinion. Points have no cash value, cannot be redeemed, transferred or sold, are not payment for a review, and we may change
          or withdraw the points programme at any time.
        </p>
      </>
    ),
  },
  {
    id: "verification",
    title: "Verification and what it does not mean",
    body: (
      <>
        <p>
          Before publishing we run automated checks, currently including confirming that the reel is public, that a person is visibly
          speaking on camera (using Meta SAM 3.1), transcribing the audio (Muse Voice Transcribe) and extracting the review (Muse Spark).
          These checks are designed to filter out slideshows, screen recordings, voice-overs and obviously off-topic content.
        </p>
        <p>
          <strong>Verification is not an identity check and not a guarantee.</strong> We do not confirm who the reviewer is, that the visit
          took place, or that any statement is accurate. A &ldquo;verified&rdquo; label or the presence of a review on {B} means only that
          our automated checks passed at the time of submission. Automated systems make mistakes; see section 7 on AI output.
        </p>
      </>
    ),
  },
  {
    id: "content-rules",
    title: "Content rules",
    body: (
      <>
        <p>You may not submit, and we may remove without notice, content that:</p>
        <ul>
          <li>is defamatory, knowingly false, or misleading about a business or any person;</li>
          <li>is hateful, harassing, threatening or discriminatory on the basis of race, ethnicity, national origin, religion, sex, gender, sexual orientation, disability, age or any other protected characteristic;</li>
          <li>is sexually explicit, depicts violence or self-harm, or promotes illegal activity;</li>
          <li>discloses another person&rsquo;s private information (home address, phone number, financial or health details) or shows identifiable people who have not consented to appear;</li>
          <li>infringes anyone&rsquo;s copyright, trade mark, privacy, publicity or other rights, including by using music or footage you have no right to use;</li>
          <li>is spam, duplicative, automated, machine-generated, or part of a coordinated campaign for or against a business;</li>
          <li>contains malware, phishing links, or attempts to manipulate our systems or the AI pipeline (for example, spoken instructions aimed at the model);</li>
          <li>violates Instagram&rsquo;s or WhatsApp&rsquo;s terms, or any applicable law.</li>
        </ul>
        <p>
          We may also remove or decline content that does not meet our quality bar, such as inaudible audio, no identifiable business, or a
          review of a business that does not appear to exist.
        </p>
      </>
    ),
  },
  {
    id: "ai",
    title: "AI-generated transcripts, extractions and summaries",
    body: (
      <>
        <p>
          Transcripts, structured review fields, sentiment labels, keyword tags, recommendation rates and the per-business AI summary are
          produced automatically by machine learning models without human review. They may be incomplete, mistranslated, mis-attributed,
          or wrong, particularly for accents, code-switching between languages, and noisy audio.
        </p>
        <p>
          AI summaries aggregate the opinions of reviewers; they are not statements of fact by {B}, nor our opinion. A summary is regenerated
          whenever a new review is published and will change over time. You should watch the underlying reels before relying on anything you
          read on {B}, and you must not present our AI output as an independent assessment.
        </p>
        <p>
          If you believe an AI output misrepresents what you said in your reel, contact us at <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a>{" "}
          or via the WhatsApp number from which you submitted, and we will review it.
        </p>
      </>
    ),
  },
  {
    id: "licence",
    title: "Your content and the licence you give us",
    body: (
      <>
        <p>
          You keep all rights you have in your reel and anything you say in it. The reel itself remains hosted by Instagram and is displayed on
          {" "}{B} through Instagram&rsquo;s official embed, subject to Instagram&rsquo;s terms.
        </p>
        <p>
          So that we can operate the Service, you grant {B} a worldwide, non-exclusive, royalty-free, sublicensable (to our service providers
          only) licence to: download and store a working copy of your reel and its audio; process it with automated systems; create,
          store, display and distribute transcripts, extracted review data, summaries and other derivative works based on it; and display your
          Instagram display name or handle alongside the review. This licence lasts for as long as the review is published on {B} and for a
          reasonable period afterwards to allow for backups, dispute handling and legal compliance, and continues for derived aggregate
          data (such as a business&rsquo;s recommendation rate) that no longer identifies you.
        </p>
        <p>
          You also grant us the right to use short excerpts of transcripts and your review&rsquo;s structured fields to describe the Service,
          for example in search results or social previews. We will not use your face or voice to train machine learning models.
        </p>
        <p>
          You may withdraw a review at any time (section 10). Withdrawal ends the licence for that review except as described above.
        </p>
      </>
    ),
  },
  {
    id: "businesses",
    title: "If you are a business listed on the Service",
    body: (
      <>
        <p>
          Business names, addresses, categories and locations are drawn from Google&rsquo;s Places data or from the reviewer&rsquo;s own
          description, and are displayed for identification only. A listing on {B} does not imply any relationship with us, and you do not
          need an account to be listed.
        </p>
        <p>
          We do not remove honest reviews at a business&rsquo;s request and we do not sell review removal, ranking, or favourable summaries. If
          you believe a review violates these Terms (for example, it is about a different business, it is defamatory, or it was posted by a
          competitor), send a notice under section 11. If you believe listing information is wrong, email{" "}
          <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a> with the business page link and the correction.
        </p>
        <p>
          You must not offer reviewers money, discounts or other incentives in exchange for positive reviews, pressure reviewers to withdraw
          reviews, or submit reviews of your own business or a competitor&rsquo;s without disclosure. Doing so is a breach of these Terms
          and may be unlawful consumer-protection practice in your country.
        </p>
      </>
    ),
  },
  {
    id: "removal",
    title: "Withdrawing or removing a review",
    body: (
      <>
        <p>
          <strong>By the reviewer.</strong> You may ask us to remove your review at any time by messaging the {B} WhatsApp number from the same
          phone number you submitted with, or by emailing <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a> from an address you
          can verify. We will remove the review from the website and delete our stored copy of the video and audio within 30 days, keeping
          only what we must retain under section 12 of the Privacy Policy. Deleting or privatising the reel on Instagram does not by itself
          notify us; please message us too.
        </p>
        <p>
          <strong>By us.</strong> We may remove, hide, edit the metadata of, or refuse to publish any content at any time, with or without
          notice, if we reasonably believe it breaches these Terms, exposes us or others to liability, or harms the integrity of the Service.
          We may also suspend or block phone numbers or Instagram accounts that repeatedly breach these Terms.
        </p>
        <p>
          We generally notify reviewers over WhatsApp when a review is removed for a Terms violation and give them a chance to respond, unless
          doing so would be unlawful or harmful.
        </p>
      </>
    ),
  },
  {
    id: "complaints",
    title: "Complaints, takedown notices and counter-notices",
    body: (
      <>
        <p>
          If you believe content on {B} is defamatory, infringes your intellectual property, or otherwise violates these Terms or your legal
          rights, email <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a> with:
        </p>
        <ol>
          <li>the link to the business page and the review in question;</li>
          <li>your name, organisation (if any) and contact details;</li>
          <li>a description of the content you object to and the right you say it infringes or the rule it breaks;</li>
          <li>for intellectual-property claims, evidence that you own the right and a statement, made in good faith, that the use is not authorised;</li>
          <li>a statement that the information in your notice is accurate.</li>
        </ol>
        <p>
          We aim to acknowledge notices within 5 business days and to act on well-founded notices within 14 days. Where we remove content
          in response to a notice, we will tell the reviewer and may give them an opportunity to submit a counter-notice. We may share your
          notice with the reviewer. Knowingly false notices may make you liable for resulting costs.
        </p>
      </>
    ),
  },
  {
    id: "acceptable-use",
    title: "Acceptable use of the website and API",
    body: (
      <>
        <p>You agree not to:</p>
        <ul>
          <li>scrape, crawl, bulk-download or systematically extract data from the Service except through any public API we document, and then only within its stated limits;</li>
          <li>use the Service to build or train a competing review dataset or model;</li>
          <li>circumvent, disable or interfere with security features, rate limits or the verification pipeline;</li>
          <li>misrepresent your affiliation with {B}, a reviewer or a business;</li>
          <li>send unsolicited messages to our WhatsApp number that are not review submissions or related queries;</li>
          <li>use the Service in a way that violates applicable law, including consumer protection, data protection and anti-spam laws.</li>
        </ul>
        <p>
          Businesses and researchers may use published summaries and recommendation rates with attribution to {B} and a link to the business
          page, provided the use is not misleading and respects the rights of reviewers.
        </p>
      </>
    ),
  },
  {
    id: "ip",
    title: "Our intellectual property",
    body: (
      <>
        <p>
          The {B} name, logo, website design, software and the compilation of reviews and summaries are owned by {LEGAL.operator} or our
          licensors. Our source code is published under an open-source licence in our public repository; that licence, not these Terms,
          governs the code. Nothing in these Terms gives you a right to use our name or logo without written permission.
        </p>
        <p>
          Instagram, WhatsApp and the Meta model names are trade marks of Meta Platforms, Inc. Google Maps and Google Places are trade marks
          of Google LLC. {B} is not affiliated with or endorsed by Meta or Google.
        </p>
      </>
    ),
  },
  {
    id: "third-parties",
    title: "Third-party services",
    body: (
      <>
        <p>
          The Service relies on third parties, including Instagram (hosting and embedding reels), WhatsApp (receiving submissions), Meta&rsquo;s
          model APIs (face check, transcription, extraction), Google (place data, map links and Google reviews) and Amazon Web Services
          (hosting). Their terms and privacy policies apply to your use of their services. We are not responsible for their availability,
          content or conduct, and embedded Instagram content may set cookies or collect data under Meta&rsquo;s policies.
        </p>
        <p>
          Where a business page shows <strong>reviews from Google</strong>, that content is fetched live from Google Places when you open
          the page and is shown as written by its authors; we do not store it, and we cache only the Google place identifier and our
          AI-generated summary of those reviews for up to 24 hours. Google reviews are Google&rsquo;s content and are subject to
          Google&rsquo;s terms, not ours.
        </p>
      </>
    ),
  },
  {
    id: "disclaimers",
    title: "Disclaimers",
    body: (
      <>
        <p>
          The Service is provided <strong>&ldquo;as is&rdquo;</strong> and <strong>&ldquo;as available&rdquo;</strong>. To the fullest extent
          permitted by law, we disclaim all warranties, express or implied, including merchantability, fitness for a particular purpose,
          non-infringement, accuracy and uninterrupted or error-free operation. We do not warrant that reviews are truthful, that
          businesses are as described, that AI outputs are accurate, or that any business is safe, licensed or suitable for you. Your
          decisions to visit or transact with a business are your own.
        </p>
        <p>
          Nothing in these Terms limits rights you have as a consumer under mandatory law in your country of residence.
        </p>
      </>
    ),
  },
  {
    id: "liability",
    title: "Limitation of liability",
    body: (
      <>
        <p>
          To the fullest extent permitted by law, {LEGAL.operator} and its officers, employees, contractors and partners will not be liable
          for any indirect, incidental, special, consequential or punitive damages, or for loss of profits, revenue, goodwill, data or
          business opportunity, arising out of or related to the Service or these Terms, even if advised of the possibility.
        </p>
        <p>
          Our total aggregate liability for all claims relating to the Service in any twelve-month period will not exceed the greater of (a)
          the amount you paid us for the Service in that period (currently nothing) and (b) USD 100 or its equivalent.
        </p>
        <p>
          These limits do not apply to liability for death or personal injury caused by negligence, for fraud or fraudulent misrepresentation,
          or for anything that cannot be limited by law.
        </p>
      </>
    ),
  },
  {
    id: "indemnity",
    title: "Your responsibility for your content",
    body: (
      <p>
        You agree to indemnify and hold harmless {LEGAL.operator} from claims, damages, liabilities and reasonable costs (including legal fees)
        arising from your content, your breach of these Terms, or your violation of any law or third-party right, including defamation and
        intellectual-property claims brought by a business or person you reviewed. We will notify you of any such claim and may take over its
        defence at our expense.
      </p>
    ),
  },
  {
    id: "changes",
    title: "Changes to the Service and these Terms",
    body: (
      <>
        <p>
          We are an early-stage service and may change, suspend or discontinue any part of the Service at any time, including the verification
          pipeline, the models we use, the categories we support and the countries we cover. We may also set limits on submissions.
        </p>
        <p>
          We may update these Terms. When we do, we will change the &ldquo;Effective&rdquo; date above and, for material changes, post a
          notice on the website or message active reviewers over WhatsApp at least 14 days before they take effect. Continued use after the
          effective date constitutes acceptance. If you do not agree, stop using the Service and you may withdraw your reviews.
        </p>
      </>
    ),
  },
  {
    id: "termination",
    title: "Termination",
    body: (
      <p>
        You may stop using the Service at any time and request removal of your reviews. We may suspend or terminate your ability to submit
        content, with or without notice, if you breach these Terms or if we discontinue the Service. Sections that by their nature should
        survive (including licence to derived aggregate data, disclaimers, limitation of liability, indemnity and governing law) survive
        termination.
      </p>
    ),
  },
  {
    id: "law",
    title: "Governing law and disputes",
    body: (
      <>
        <p>
          These Terms are governed by the laws of {LEGAL.governingLaw}, without regard to conflict-of-law rules. Before bringing a claim, you
          agree to contact us at <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a> and attempt in good faith to resolve the
          dispute informally for at least 30 days. Subject to any mandatory consumer rights to bring proceedings where you live, disputes
          will be resolved exclusively in {LEGAL.courts}.
        </p>
        <p>
          If any provision of these Terms is held unenforceable, the rest remains in effect. Our failure to enforce a provision is not a
          waiver. These Terms, together with the Privacy Policy, are the entire agreement between you and us about the Service. You may not
          assign these Terms; we may assign them to a successor of the Service.
        </p>
      </>
    ),
  },
  {
    id: "contact",
    title: "Contact",
    body: (
      <>
        <p>
          {LEGAL.operator}
          <br />
          {LEGAL.address}
          <br />
          Legal and takedown notices: <a href={`mailto:${LEGAL.legalEmail}`}>{LEGAL.legalEmail}</a>
          <br />
          Privacy requests: <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>
        </p>
      </>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      kicker="Legal"
      title="Terms of Service"
      effective={LEGAL.termsEffective}
      related={{ href: "/privacy", label: "Privacy Policy" }}
      intro={
        <p>
          These Terms explain the rules for using {B}: how video reviews are submitted and verified, what you promise when you submit one,
          how businesses can raise concerns, and the limits of what we are responsible for. Please read them; they affect your rights.
        </p>
      }
      summary={[
        `You must be ${LEGAL.minimumAge} or older to submit a review, and it must be your own public Instagram reel about a business you actually visited.`,
        "Be honest, and say so in the video if you have any connection to the business or were given anything for the review.",
        "Our checks confirm a real person is speaking on camera; they do not verify identity or facts, and AI transcripts and summaries can be wrong.",
        "You keep your rights; you give us a licence to process, store a copy of, and display your reel and the review we extract from it.",
        "You can withdraw a review at any time via WhatsApp or email. We never charge businesses to remove or improve reviews.",
        "Businesses and anyone else can send a takedown notice; we act on well-founded notices within 14 days.",
        `The Service is provided as is, our liability is capped, and ${LEGAL.governingLawAdjective} law applies.`,
      ]}
      sections={sections}
    />
  );
}
