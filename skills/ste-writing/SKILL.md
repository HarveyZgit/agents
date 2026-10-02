---
name: ste-writing
description: 用短句、固定用词、一句一事的受控写法解释或改写一段内容，让人一遍读懂、不产生歧义。当用户觉得输出太冗长、太绕、看不懂，要求「写清楚一点」「换个说法」「别这么啰嗦」，或点名 STE / ASD-STE100 时使用。Use when the user finds an explanation too long, convoluted, or hard to follow and asks for a clearer, plainer rewrite, or asks for STE / ASD-STE100.
metadata:
  version: 1.0.0
---

# ste-writing

Explain, or rewrite, in the style of ASD-STE100 (Simplified Technical English): a controlled language made for maintenance documentation that must be understood correctly by non-native readers on the first read. Its rules trade expressiveness for clarity, which makes it a good default when the reader needs to understand model output quickly and check it for errors.

## Strictness

- Default to **about 80% of the way to the spec**: keep the sentence and structure rules below, but allow a general-English word when no approved word says the same thing. The full dictionary is stringent and makes some topics awkward.
- Go **full STE** only when the user asks for it (for example "strict STE", "full ASD-STE100", or when the text is a procedure or safety instruction).
- Do not change the meaning. If the source is ambiguous, say what is ambiguous instead of guessing.

## Sentence rules

- One topic per sentence. In procedures, one instruction per sentence.
- Keep sentences short: at most 20 words for instructions, at most 25 words for descriptions. Keep paragraphs to at most 6 sentences.
- Use the active voice. Name who or what does the action.
- Use simple verb forms only: imperative, simple present, simple past, future with "will". Do not use "-ing" forms as verbs, and do not use the present progressive.
- Write instructions as commands ("Remove the cover"), not as descriptions of what someone could do.
- Do not stack more than three nouns in a row. Break a long noun cluster into a phrase.
- Keep the articles "a", "an", "the" and demonstratives like "this". Do not drop them to save space.
- Avoid pronouns that can point to more than one thing. Repeat the noun instead of writing "it" or "they".
- Put a warning or caution before the step it applies to, and start it with a clear command or condition.
- Use a vertical list when a sentence would otherwise hold more than two items or more than one condition.

## Word rules

- Use one word for one thing, and use the same word every time. Do not vary vocabulary for style.
- Give each word one meaning. Prefer the most common meaning ("close" means "to shut", not "near").
- Prefer short, common words: "start" over "initiate", "use" over "utilize", "about" over "approximately".
- Technical names (the names of parts, systems, tools, commands, file formats) are allowed as they are. Do not rename them to approved words.
- Do not use idioms, slang, humor, or hedging fillers ("basically", "sort of", "it should be noted that").
- Replace vague quantities ("a few", "some", "many") with a number or a range when the source gives one.

## Working method

1. Identify the reader and the goal: what must the reader be able to do or decide after reading?
2. Split the source into facts and steps. Drop anything that does not serve the goal.
3. Rewrite fact by fact under the rules above. Keep original terms, numbers, and names exact.
4. Reread the result as the reader. Any sentence that needs a second read is a sentence to split or simplify.
5. If the text is a rewrite of the user's own material, show only the rewritten text unless the user asks for a change list.

## When text is not enough

Writing is the first rung. If the reader still has to hold too much in their head, say so and offer the next rung instead of a longer text: a diagram, a self-contained interactive page, or a short explainer video. Custom, discardable artifacts are cheap now; a throwaway page that makes a structure visible is often a better deliverable than another paragraph.
