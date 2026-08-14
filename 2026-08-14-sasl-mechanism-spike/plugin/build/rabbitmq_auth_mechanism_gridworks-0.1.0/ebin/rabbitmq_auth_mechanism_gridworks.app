{application, rabbitmq_auth_mechanism_gridworks, [
  {description, "GridWorks SASL mechanism: cert identity + claims"},
  {vsn, "0.1.0"},
  {modules, [rabbit_auth_mechanism_gridworks]},
  {registered, []},
  {applications, [kernel, stdlib, rabbit]},
  {env, []}
]}.
