-- V2.5.98 — backup cover credit-only ledger
-- Real completed cover awards a credit only to the covering resident.
-- The covered resident receives no debt and no existing credit is consumed.

ALTER TABLE public.backup_cover_events
  ALTER COLUMN covered_ref_id DROP NOT NULL;

ALTER TABLE public.backup_cover_events
  DROP CONSTRAINT IF EXISTS backup_cover_events_covered_effect_check;
ALTER TABLE public.backup_cover_events
  ADD CONSTRAINT backup_cover_events_covered_effect_check
  CHECK (covered_effect IN ('DEBT_INCURRED','REST_CONSUMED','NONE'));

CREATE OR REPLACE FUNCTION public.complete_backup_cover_v255(p_backup_id bigint)
RETURNS TABLE(coverer text, covered_person text, credit_type text, coverer_effect text, covered_effect text)
LANGUAGE plpgsql
SET search_path TO 'public', 'auth'
AS $function$
DECLARE
  b public.backup_assignments%rowtype;
  v_coverer text;
  v_covered text;
  v_type text;
  v_credit_ref bigint;
BEGIN
  IF NOT public.is_senior(auth.uid()) THEN RAISE EXCEPTION 'Senior only'; END IF;
  SELECT * INTO b FROM public.backup_assignments WHERE id=p_backup_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Backup not found'; END IF;
  IF b.completed_at IS NOT NULL THEN RAISE EXCEPTION 'Backup already completed'; END IF;

  v_coverer:=coalesce(b.actual_backup,b.planned_backup);
  v_covered:=b.covered_person;
  v_type:=CASE upper(coalesce(b.covered_block,''))
    WHEN 'AM' THEN 'AM' WHEN 'PM' THEN 'PM' WHEN 'NIGHT' THEN 'NIGHT' ELSE NULL END;
  IF v_coverer IS NULL OR v_covered IS NULL OR v_type IS NULL THEN
    RAISE EXCEPTION 'Backup row lacks coverer, covered person, or supported block';
  END IF;

  INSERT INTO public.backup_credit_earnings(initials,source_backup_id,units,cover_kind,cover_hours,credit_type,expires_at)
  VALUES(v_coverer,p_backup_id,1,lower(v_type),CASE WHEN v_type='NIGHT' THEN 12 ELSE 6 END,v_type,now()+interval '12 months')
  RETURNING id INTO v_credit_ref;

  UPDATE public.backup_assignments
  SET completed_at=now(),completed_by=auth.uid(),updated_at=now()
  WHERE id=p_backup_id;

  INSERT INTO public.backup_cover_events(backup_id,coverer,covered_person,credit_type,coverer_effect,coverer_ref_id,covered_effect,covered_ref_id)
  VALUES(p_backup_id,v_coverer,v_covered,v_type,'REST_EARNED',v_credit_ref,'NONE',NULL);

  RETURN QUERY SELECT v_coverer,v_covered,v_type,'REST_EARNED'::text,'NONE'::text;
END;
$function$;

CREATE OR REPLACE FUNCTION public.undo_backup_credit(p_backup_id bigint)
RETURNS void
LANGUAGE plpgsql
SET search_path TO 'public', 'auth'
AS $function$
DECLARE
  ev public.backup_cover_events%rowtype;
  e public.backup_credit_earnings%rowtype;
BEGIN
  IF NOT public.is_senior(auth.uid()) THEN RAISE EXCEPTION 'Senior only'; END IF;

  SELECT * INTO ev FROM public.backup_cover_events WHERE backup_id=p_backup_id FOR UPDATE;
  IF NOT FOUND THEN
    DELETE FROM public.backup_credit_earnings
      WHERE source_backup_id=p_backup_id AND redeemed_at IS NULL AND consumed_at IS NULL;
    UPDATE public.backup_assignments SET completed_at=NULL,completed_by=NULL,updated_at=now() WHERE id=p_backup_id;
    RETURN;
  END IF;

  SELECT * INTO e FROM public.backup_credit_earnings WHERE id=ev.coverer_ref_id FOR UPDATE;
  IF FOUND AND (e.redeemed_at IS NOT NULL OR e.consumed_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Cannot undo: earned rest credit has already been used';
  END IF;

  DELETE FROM public.backup_credit_earnings WHERE id=ev.coverer_ref_id;
  DELETE FROM public.backup_cover_events WHERE backup_id=p_backup_id;
  UPDATE public.backup_assignments SET completed_at=NULL,completed_by=NULL,updated_at=now() WHERE id=p_backup_id;
END;
$function$;

-- Legacy work-debt rows are intentionally not used by V2.5.98.
-- There are no production rows at migration time; the table is retained only for schema compatibility.
