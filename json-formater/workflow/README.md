# JSON Formatter Alfred Workflow

Keyword: `json`

## Usage

- `json {"a":1}` parses the text typed in Alfred.
- `json` with no argument reads the current clipboard.

The workflow repeatedly parses JSON strings. If JSON parsing fails, it tries Python literal deserialization. The final value is written to Alfred's workflow cache directory as a `.json` file. The script prints the file URL, and Alfred's Open URL action opens it in the default browser.

Generated files live under `$alfred_workflow_cache`. The workflow does not delete them itself; cache removal is left to Alfred/macOS cache handling and Alfred's workflow data/cache deletion flow.

## Examples

Input:

```json
"\"{\\\"a\\\":1}\""
```

Output file:

```json
{
  "a": 1
}
```

Python literal fallback input:

```python
{'a': 1, 'b': True}
```

Output file:

```json
{
  "a": 1,
  "b": true
}
```
