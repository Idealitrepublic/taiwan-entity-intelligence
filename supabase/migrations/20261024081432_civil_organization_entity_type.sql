-- An organization in an official association roster is not a company or person.
-- Existing entities/evidence publication RLS and search RPC apply unchanged.
insert into public.entity_types (code) values ('CivilOrganization')
on conflict (code) do nothing;
