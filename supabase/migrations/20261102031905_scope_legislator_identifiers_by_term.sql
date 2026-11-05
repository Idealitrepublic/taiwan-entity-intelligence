-- Add source/term-scoped aliases without changing any entity or foreign key.
-- Legacy identifiers are compatible only with term 11.
DO $$ BEGIN
 IF EXISTS (
  SELECT 1 FROM public.politician_terms t
  JOIN public.entity_identifiers i ON i.entity_id=t.politician_entity_id
  WHERE i.namespace='tw:legislative_yuan:legislator_number'
  AND t.term_number<>11 AND t.publication_status='published'
 ) THEN RAISE EXCEPTION 'Legacy cross-term identity requires manual review'; END IF;
END $$;
INSERT INTO public.entity_identifiers(entity_id,namespace,value,confidence)
SELECT DISTINCT t.politician_entity_id, 'tw:legislative_yuan:id14:term:11', t.legislator_number, 'EXACT'
FROM public.politician_terms t
JOIN public.entity_identifiers i ON i.entity_id=t.politician_entity_id
 AND i.namespace='tw:legislative_yuan:legislator_number' AND i.value=t.legislator_number
WHERE t.term_number=11
AND NOT EXISTS (SELECT 1 FROM public.entity_identifiers n
 WHERE n.namespace='tw:legislative_yuan:id14:term:11' AND n.value=t.legislator_number
 AND n.entity_id=t.politician_entity_id);

create or replace function tei_private.validate_politician_term() returns trigger
language plpgsql set search_path = '' as $$
declare politician public.entities; party public.entities; proof public.evidence_records;
begin
  if new.publication_status <> 'published' then return new; end if;
  select * into politician from public.entities where id = new.politician_entity_id for share;
  if politician.entity_type <> 'Politician' or politician.publication_status <> 'published' then
    raise exception 'Published term requires a published Politician entity' using errcode='23514';
  end if;
  if new.party_entity_id is not null then
    select * into party from public.entities where id = new.party_entity_id for share;
    if party.entity_type <> 'PoliticalParty' or party.publication_status <> 'published' then
      raise exception 'Published term party must be a published PoliticalParty entity' using errcode='23514';
    end if;
  end if;
  if new.legislator_number is not null and not exists (
    select 1 from public.entity_identifiers identifier
    where identifier.entity_id = new.politician_entity_id
      and (identifier.namespace = 'tw:legislative_yuan:id14:term:' || new.term_number::text
        or (new.term_number = 11 and identifier.namespace = 'tw:legislative_yuan:legislator_number'))
      and identifier.value = new.legislator_number
  ) then
    raise exception 'Published term legislator number must exactly identify its Politician'
      using errcode='23514';
  end if;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  if proof.status <> 'active' or proof.publication_status <> 'published' then
    raise exception 'Published term requires active published Evidence' using errcode='23514';
  end if;
  return new;
end $$;

