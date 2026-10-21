import { useQuery } from '@tanstack/react-query'
import { myAccessGroups } from '../../api/auth'
import { Loading } from '../../components/Feedback'

/** Groups the user may share a document with (their own groups; every group for Admins). */
export function AccessGroupPicker({ value, onChange, legend = 'Who may read this document?' }: { value: string[]; onChange: (ids: string[]) => void; legend?: string }) {
  const groups = useQuery({ queryKey: ['access-groups-mine'], queryFn: myAccessGroups })
  if (groups.isPending) return <Loading label="Loading your groups…" />
  return (
    <fieldset>
      <legend>{legend}</legend>
      {groups.data?.length === 0 && <p className="muted">You are not in any access group. Ask an Admin to add you to one.</p>}
      {groups.data?.map((group) => (
        <label key={group.id} className="check">
          <input
            type="checkbox"
            checked={value.includes(group.id)}
            onChange={() => onChange(value.includes(group.id) ? value.filter((id) => id !== group.id) : [...value, group.id])}
          />
          {group.name}
          {group.description && <span className="muted"> — {group.description}</span>}
        </label>
      ))}
      {value.length === 0 && <span className="field-error">Choose at least one group.</span>}
    </fieldset>
  )
}
